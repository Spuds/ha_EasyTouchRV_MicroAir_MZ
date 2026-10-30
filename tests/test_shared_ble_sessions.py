"""Run complete production parser classes with mocked BLE and an independent peer."""

import ast
import asyncio
import base64
import importlib.util
import inspect
import json
import logging
import time
import unittest
from collections.abc import Callable
from contextlib import asynccontextmanager
from enum import StrEnum
from functools import wraps
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "custom_components/micro_air_easytouch_mz/micro_air_easytouch"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


micro_broker_module = load("microair_broker", SOURCE / "ble_session.py")
peer_broker_module = load("independent_peer_broker", SOURCE / "ble_session.py")


class HVACMode(StrEnum):
    OFF = "off"
    HEAT = "heat"
    COOL = "cool"
    AUTO = "auto"
    FAN_ONLY = "fan_only"
    DRY = "dry"


class BleakError(Exception):
    pass


class BluetoothData:
    pass


class Tracker:
    def __init__(self):
        self.active = set()
        self.peak = 0
        self.events = []
        self.clients = []
        self.read_gate = None
        self.write_gate = None
        self.read_started = asyncio.Event()
        self.write_started = asyncio.Event()
        self.bad_payload = False
        self.fail_connect = False

    def opened(self, key):
        self.active.add(key)
        self.peak = max(self.peak, len(self.active))

    def closed(self, key):
        self.active.discard(key)


tracker = None


class Client:
    def __init__(self):
        self.is_connected = True
        self.services = True
        self.last = {}
        tracker.clients.append(self)
        tracker.opened(self)

    async def disconnect(self):
        await asyncio.sleep(0)
        self.is_connected = False
        tracker.closed(self)

    async def write_gatt_char(self, uuid, payload, response):
        assert self.is_connected
        if uuid == ns["UUIDS"]["passwordCmd"]:
            tracker.events.append(("auth", None))
            return
        command = json.loads(payload)
        self.last = command
        tracker.events.append(
            (
                command["Type"],
                command.get("Zone", command.get("Changes", {}).get("zone")),
            )
        )
        if command["Type"] == "Change":
            tracker.write_started.set()
            if tracker.write_gate is not None:
                await tracker.write_gate.wait()

    async def read_gatt_char(self, uuid):
        tracker.read_started.set()
        if tracker.read_gate is not None:
            await tracker.read_gate.wait()
        if tracker.bad_payload:
            return b"not JSON"
        if self.last.get("Type") == "Get Config":
            return json.dumps(
                {
                    "Type": "Response",
                    "RT": "Config",
                    "CFG": {"MAV": 31, "FA": [255] * 16, "SPL": [60, 85, 50, 85]},
                }
            ).encode()
        zone = [68, 75, 72, 70, 70, 50, 1, 1, 1, 1, 5, 128, 63, 45, 0, 0]
        return json.dumps(
            {"Z_sts": {"0": zone, "1": zone}, "PRM": [0, 0], "SN": "test"}
        ).encode()


async def establish_connection(client_class, device, name, **kwargs):
    if tracker.fail_connect:
        raise BleakError("unreachable")
    return Client()


ns = {
    "__name__": "microair_production_under_test",
    "asyncio": asyncio,
    "asynccontextmanager": asynccontextmanager,
    "wraps": wraps,
    "logging": logging,
    "time": time,
    "json": json,
    "base64": base64,
    "Callable": Callable,
    "StrEnum": StrEnum,
    "BluetoothData": BluetoothData,
    "BleakError": BleakError,
    "HVACMode": HVACMode,
    "BleakClientWithServiceCache": Client,
    "establish_connection": establish_connection,
    "DOMAIN": "micro_air_easytouch_mz",
    "BROKER_KEY": micro_broker_module.BROKER_KEY,
    "BleSessionBroker": micro_broker_module.BleSessionBroker,
    "FAN_OFF": "off",
    "FAN_LOW": "low",
    "FAN_HIGH": "high",
}
# Execute all production constants, functions and classes, in their original order.
# Only dependency imports are replaced by the test doubles above.
for filename in ["const.py", "parser.py"]:
    tree = ast.parse((SOURCE / filename).read_text())
    tree.body = [
        n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom))
    ]
    tree.body.insert(
        0,
        ast.ImportFrom(
            module="__future__", names=[ast.alias(name="annotations")], level=0
        ),
    )
    exec(compile(ast.fix_missing_locations(tree), str(SOURCE / filename), "exec"), ns)  # noqa: S102 - trusted production source
Parser = ns["MicroAirEasyTouchBluetoothDeviceData"]


class Peer:
    """An independent integration implementing only the documented broker hooks."""

    def __init__(self, broker, name="peer"):
        self._ble_broker = broker
        self._client = None
        self._logger = logging.getLogger("test.peer")

    async def _ensure_connected(self):
        self._client = SimpleNamespace(is_connected=True)
        tracker.opened(self)

    async def _cleanup_connection(self):
        tracker.closed(self)
        self._client = None

    async def _finish_ble_session(self):
        pass

    async def _async_update_data(self):
        async with self._ble_broker.session(self, poll=True):
            await asyncio.sleep(0)
            return {}


class Tests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        global tracker
        tracker = Tracker()
        self.hass = SimpleNamespace(data={})
        self.device = SimpleNamespace(address="00:11:22:33:44:55")
        self.parser = Parser(password="test", email="test@example.invalid")
        self.parser.set_ble_device(self.device)

    async def asyncTearDown(self):
        await self.parser.async_shutdown()

    def test_complete_class_retains_async_methods_and_versioned_broker_contract(self):
        source_tree = ast.parse((SOURCE / "parser.py").read_text())
        for cls in (n for n in source_tree.body if isinstance(n, ast.ClassDef)):
            actual = ns[cls.name]
            for method in cls.body:
                if isinstance(method, ast.AsyncFunctionDef):
                    decorated_context = any(
                        isinstance(d, ast.Name) and d.id == "asynccontextmanager"
                        for d in method.decorator_list
                    )
                    self.assertEqual(
                        inspect.iscoroutinefunction(getattr(actual, method.name)),
                        not decorated_context,
                        method.name,
                    )
        self.assertEqual(micro_broker_module.BROKER_KEY, "shared_ble_session_broker_v1")

    async def test_poll_authenticates_each_short_session_preserves_both_zones_and_cache(
        self,
    ):
        self.parser._device_state["zone_configs"] = {0: {"MAV": 31}, 1: {"MAV": 7}}
        self.assertTrue(await self.parser._poll_once(self.hass, self.device))
        stamp = self.parser._last_poll_time
        self.assertTrue(await self.parser._poll_once(self.hass, self.device))
        self.assertGreaterEqual(self.parser._last_poll_time, stamp)
        self.assertEqual(self.parser._device_state["available_zones"], [0, 1])
        self.assertEqual(self.parser._device_state["zone_configs"][1]["MAV"], 7)
        self.assertEqual(
            [e[0] for e in tracker.events], ["auth", "Get Status", "auth", "Get Status"]
        )
        self.assertIsNone(self.parser._client)
        self.assertIsNone(self.parser._connection_health_check_task)
        self.assertEqual(tracker.peak, 1)
        self.assertEqual(tracker.active, set())

    async def test_peer_first_and_microair_first_load_orders_share_one_broker(self):
        for first_module in [peer_broker_module, micro_broker_module]:
            self.hass = SimpleNamespace(
                data={micro_broker_module.BROKER_KEY: first_module.BleSessionBroker()}
            )
            self.parser._ble_adapter = None
            self.parser._ble_broker = None
            broker = self.hass.data[micro_broker_module.BROKER_KEY]
            heaters = [Peer(broker, str(i)) for i in range(4)]
            await asyncio.gather(
                self.parser._poll_once(self.hass, self.device),
                *(h._async_update_data() for h in heaters),
            )
            self.assertIs(self.parser._ble_broker, broker)
            self.assertEqual(tracker.peak, 1)
            self.assertFalse(tracker.active)

    async def test_microair_command_precedes_pending_poll_and_zone_is_preserved(self):
        broker = peer_broker_module.BleSessionBroker()
        self.hass.data[micro_broker_module.BROKER_KEY] = broker
        blocker = Peer(broker)
        async with broker.session(blocker, poll=True):
            poll = asyncio.create_task(self.parser._poll_once(self.hass, self.device))
            await asyncio.sleep(0)
            command = asyncio.create_task(
                self.parser._execute_command_safely(
                    self.hass,
                    self.device,
                    {"Type": "Change", "Changes": {"zone": 1, "heat_sp": 70}},
                )
            )
            await asyncio.sleep(0)
        await asyncio.wait_for(asyncio.gather(poll, command), 3)
        wire = [e for e in tracker.events if e[0] != "auth"]
        self.assertEqual(wire, [("Change", 1), ("Get Status", 1), ("Get Status", 0)])
        self.assertEqual(tracker.peak, 1)

    async def test_cancelled_command_waiting_global_queue_is_removed_and_never_writes(
        self,
    ):
        broker = peer_broker_module.BleSessionBroker()
        self.hass.data[micro_broker_module.BROKER_KEY] = broker
        blocker = Peer(broker)
        async with broker.session(blocker):
            request = asyncio.create_task(
                self.parser.send_command(
                    self.hass,
                    self.device,
                    {"Type": "Change", "Changes": {"zone": 1, "mode": 2}},
                )
            )
            await asyncio.sleep(0.02)
            self.assertEqual(len(broker._pending), 1)
            request.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await request
            await asyncio.wait_for(self.parser._command_queue.join(), 1)
            self.assertEqual(broker._pending, [])
        await asyncio.sleep(0.02)
        self.assertEqual(tracker.events, [])

    async def test_expiry_during_prewrite_delay_cancels_before_setting_write(self):
        self.parser._get_operation_delay = lambda hass, address, operation: (
            0.3 if operation == "write" else 0
        )
        request = asyncio.create_task(
            self.parser.send_command(
                self.hass,
                self.device,
                {"Type": "Change", "Changes": {"zone": 1, "mode": 2}},
            )
        )
        await asyncio.sleep(0.03)
        self.assertEqual(tracker.events, [("auth", None)])
        request.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await request
        await asyncio.wait_for(self.parser._command_queue.join(), 1)
        self.assertNotIn(("Change", 1), tracker.events)
        self.assertIsNone(self.parser._client)

    async def test_cancel_after_committed_write_finishes_verification_without_interrupting(
        self,
    ):
        tracker.write_gate = asyncio.Event()
        request = asyncio.create_task(
            self.parser.send_command(
                self.hass,
                self.device,
                {"Type": "Change", "Changes": {"zone": 1, "mode": 2}},
            )
        )
        await tracker.write_started.wait()
        request.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await request
        tracker.write_gate.set()
        await asyncio.wait_for(self.parser._command_queue.join(), 2)
        self.assertEqual(
            [e for e in tracker.events if e[0] != "auth"],
            [("Change", 1), ("Get Status", 1)],
        )
        self.assertIsNone(self.parser._client)

    async def test_expired_item_already_in_local_queue_is_skipped(self):
        future = asyncio.get_running_loop().create_future()
        future.cancel()
        await self.parser._command_queue.put(
            {"command": {"Type": "Change"}, "result_future": future, "committed": False}
        )
        worker = asyncio.create_task(
            self.parser._process_command_queue(self.hass, self.device)
        )
        await asyncio.wait_for(self.parser._command_queue.join(), 1)
        worker.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await worker
        self.assertFalse(tracker.events)

    async def test_cancelled_poll_disconnects_and_preserves_last_zone_values(self):
        await self.parser._poll_once(self.hass, self.device)
        cached = self.parser._device_state.copy()
        tracker.read_gate = asyncio.Event()
        tracker.read_started.clear()
        poll = asyncio.create_task(self.parser._poll_once(self.hass, self.device))
        await tracker.read_started.wait()
        poll.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await poll
        self.assertIsNone(self.parser._client)
        self.assertEqual(self.parser._device_state, cached)
        self.assertFalse(tracker.active)

    async def test_connection_failure_leaves_cache_and_does_not_starve_peer(self):
        await self.parser._poll_once(self.hass, self.device)
        cached = self.parser._device_state.copy()
        tracker.fail_connect = True
        with self.assertRaises(BleakError):
            await self.parser._poll_once(self.hass, self.device)
        self.assertEqual(self.parser._device_state, cached)
        heater = Peer(self.parser._ble_broker)
        await asyncio.wait_for(heater._async_update_data(), 1)
        self.assertFalse(tracker.active)

    async def test_poll_deadline_disconnects_before_other_integration_enters(self):
        self.hass.data[micro_broker_module.BROKER_KEY] = (
            micro_broker_module.BleSessionBroker()
        )
        original = micro_broker_module.POLL_TIMEOUT
        micro_broker_module.POLL_TIMEOUT = 0.02
        tracker.read_gate = asyncio.Event()
        try:
            with self.assertRaises(TimeoutError):
                await self.parser._poll_once(self.hass, self.device)
        finally:
            micro_broker_module.POLL_TIMEOUT = original
        self.assertFalse(tracker.active)
        heater = Peer(self.parser._ble_broker)
        await heater._async_update_data()
        self.assertEqual(tracker.peak, 1)

    async def test_reconnect_disconnects_still_connected_old_client_before_replacing(
        self,
    ):
        async with self.parser._ble_session(self.hass, self.device):
            old = self.parser._client
            self.assertTrue(old.is_connected)
            self.assertTrue(
                await self.parser._reconnect_and_authenticate(self.hass, self.device)
            )
            self.assertFalse(old.is_connected)
            self.assertIsNot(self.parser._client, old)
            self.assertEqual(tracker.peak, 1)
        self.assertFalse(tracker.active)

    async def test_failed_old_disconnect_prevents_reconnect_and_retains_reference(self):
        async with self.parser._ble_session(self.hass, self.device):
            old = self.parser._client
            original = old.disconnect

            async def unconfirmed():
                pass  # Proxy still reports the link connected.

            old.disconnect = unconfirmed
            self.assertFalse(
                await self.parser._reconnect_and_authenticate(self.hass, self.device)
            )
            self.assertIs(self.parser._client, old)
            self.assertEqual(len(tracker.clients), 1)
            old.disconnect = original
        self.assertFalse(tracker.active)

    async def test_authentication_error_uses_bounded_cleanup_retaining_unconfirmed_client(
        self,
    ):
        async with self.parser._ble_session(self.hass, self.device):
            old = self.parser._client
            original_disconnect = old.disconnect
            original_write = old.write_gatt_char

            async def unconfirmed():
                pass

            async def fail_auth(*args, **kwargs):
                raise BleakError("auth failure")

            old.disconnect = unconfirmed
            old.write_gatt_char = fail_auth
            # Call the real undecorated body once, avoiding retry sleeps in a
            # deliberate permanent disconnect failure. Its reference must survive.
            with self.assertRaises(BleakError):
                await Parser.authenticate.__wrapped__(self.parser, "test")
            self.assertIs(self.parser._client, old)
            self.assertEqual(len(tracker.clients), 1)
            old.disconnect = original_disconnect
            old.write_gatt_char = original_write
        self.assertFalse(tracker.active)

    async def test_startup_config_fetch_and_zone_probe_use_same_lease(self):
        await self.parser._refetch_zone_configurations(self.hass, self.device, [0, 1])
        self.assertEqual(set(self.parser._device_state["zone_configs"]), {0, 1})
        self.assertIsNone(self.parser._client)
        self.assertEqual(
            await self.parser.get_available_zones(self.hass, self.device), [0, 1]
        )
        self.assertEqual(set(self.parser._device_state["zone_configs"]), {0, 1})
        self.assertFalse(tracker.active)
        self.assertEqual(tracker.peak, 1)

    async def test_shutdown_cancels_tracked_startup_read_and_releases_slot(self):
        tracker.read_gate = asyncio.Event()
        fetch = asyncio.create_task(
            self.parser._refetch_zone_configurations(self.hass, self.device, [0, 1])
        )
        await tracker.read_started.wait()
        await asyncio.wait_for(self.parser.async_shutdown(), 2)
        self.assertTrue(fetch.cancelled())
        self.assertFalse(tracker.active)
        self.assertIsNone(self.parser._client)

    async def test_unleased_hardware_entry_is_rejected(self):
        with self.assertRaises(RuntimeError):
            await self.parser._connect_to_device(self.device)
        self.assertFalse(tracker.events)

    async def test_bad_status_keeps_cached_zones_and_reports_failed_poll(self):
        await self.parser._poll_once(self.hass, self.device)
        cached = self.parser._device_state.copy()
        tracker.bad_payload = True
        self.assertFalse(await self.parser._poll_once(self.hass, self.device))
        self.assertEqual(self.parser._device_state, cached)
        self.assertFalse(self.parser._last_poll_success)
        self.assertFalse(tracker.active)


if __name__ == "__main__":
    unittest.main()
