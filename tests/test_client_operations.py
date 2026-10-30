"""Run complete production parser classes with mocked BLE and an independent peer."""

import ast
import asyncio
import base64
import inspect
import json
import logging
import time
import unittest
import unittest.mock
from collections.abc import Callable
from contextlib import asynccontextmanager
from enum import StrEnum
from functools import wraps
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "custom_components/micro_air_easytouch_mz/micro_air_easytouch"


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
    "retry_bluetooth_connection_error": lambda **kwargs: lambda f: f,
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


class Tests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        global tracker
        tracker = Tracker()
        self.hass = SimpleNamespace(data={})
        self.device = SimpleNamespace(address="00:11:22:33:44:55")
        self.parser = Parser(password="test", email="test@example.invalid")
        self.parser.set_ble_device(self.device)
        self.parser._get_operation_delay = lambda *args: 0

    async def asyncTearDown(self):
        await self.parser.async_shutdown()

    def test_full_class_preserves_async_methods(self):
        tree = ast.parse((SOURCE / "parser.py").read_text())
        for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
            for method in cls.body:
                if isinstance(method, ast.AsyncFunctionDef):
                    context = any(
                        isinstance(d, ast.Name) and d.id == "asynccontextmanager"
                        for d in method.decorator_list
                    )
                    self.assertEqual(
                        inspect.iscoroutinefunction(getattr(ns[cls.name], method.name)),
                        not context,
                    )

    async def test_repeated_poll_authenticates_once_and_preserves_both_zones(self):
        self.parser._device_state["zone_configs"] = {0: {"MAV": 31}, 1: {"MAV": 7}}
        self.parser._poll_interval = 0.01
        count = 0
        done = asyncio.Event()
        original = Client.read_gatt_char

        async def read(client, uuid):
            nonlocal count
            result = await original(client, uuid)
            count += 1
            if count >= 2:
                done.set()
            return result

        with unittest.mock.patch.object(Client, "read_gatt_char", read):
            task = asyncio.create_task(self.parser._poll_loop(self.hass))
            await asyncio.wait_for(done.wait(), 5)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(len(tracker.clients), 1)
        self.assertEqual([e[0] for e in tracker.events].count("auth"), 1)
        self.assertTrue(self.parser._client.is_connected)
        self.assertEqual(self.parser._device_state["available_zones"], [0, 1])
        self.assertEqual(self.parser._device_state["zone_configs"][1]["MAV"], 7)

    async def test_expired_command_waiting_for_client_lock_never_writes(self):
        future = asyncio.get_running_loop().create_future()
        async with self.parser._client_operation():
            task = asyncio.create_task(
                self.parser._execute_command_safely(
                    self.hass,
                    self.device,
                    {"Type": "Change", "Changes": {"zone": 1}},
                    request={"result_future": future},
                )
            )
            await asyncio.sleep(0)
            future.cancel()
            self.assertFalse(task.done())
        self.assertFalse(await task)
        self.assertEqual(tracker.events, [])

    async def test_two_parsers_have_independent_locks(self):
        other = Parser(password="test", email="test@example.invalid")
        try:
            async with self.parser._client_operation():

                async def acquire():
                    async with other._client_operation():
                        return True

                self.assertTrue(await asyncio.wait_for(acquire(), 1))
        finally:
            await other.async_shutdown()

    async def test_cleanup_waits_for_command_lock_and_retains_cache(self):
        await self.parser._ensure_connected(self.hass, self.device)
        client = self.parser._client
        self.parser._device_state = {"available_zones": [0, 1]}
        async with self.parser._client_operation():
            cleanup = asyncio.create_task(self.parser._disconnect_safely())
            await asyncio.sleep(0)
            self.assertFalse(cleanup.done())
            self.assertTrue(client.is_connected)
        await cleanup
        self.assertFalse(client.is_connected)
        self.assertEqual(self.parser._device_state["available_zones"], [0, 1])

    async def test_queued_expired_request_is_discarded(self):
        future = asyncio.get_running_loop().create_future()
        future.cancel()
        await self.parser._command_queue.put(
            {"command": {"Type": "Change"}, "result_future": future}
        )
        worker = asyncio.create_task(
            self.parser._process_command_queue(self.hass, self.device)
        )
        await asyncio.wait_for(self.parser._command_queue.join(), 1)
        worker.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await worker
        self.assertEqual(tracker.events, [])

    async def test_multizone_command_and_verification_remain_atomic(self):
        tracker.write_gate = asyncio.Event()
        first = asyncio.create_task(
            self.parser._execute_command_safely(
                self.hass,
                self.device,
                {"Type": "Change", "Changes": {"zone": 1, "mode": 1}},
            )
        )
        await tracker.write_started.wait()
        second = asyncio.create_task(
            self.parser._execute_command_safely(
                self.hass,
                self.device,
                {"Type": "Change", "Changes": {"zone": 0, "mode": 1}},
            )
        )
        await asyncio.sleep(0)
        self.assertEqual([e[0] for e in tracker.events], ["auth", "Change"])
        tracker.write_gate.set()
        self.assertTrue(all(await asyncio.wait_for(asyncio.gather(first, second), 3)))
        self.assertEqual(
            tracker.events,
            [
                ("auth", None),
                ("Change", 1),
                ("Get Status", 1),
                ("Change", 0),
                ("Get Status", 0),
            ],
        )
        self.assertEqual(self.parser._device_state["available_zones"], [0, 1])
        self.assertEqual(len(tracker.clients), 1)
        self.assertTrue(self.parser._client.is_connected)

    async def test_expired_during_connect_never_writes_setting(self):
        future = asyncio.get_running_loop().create_future()

        async def connect(*args):
            future.cancel()
            return True

        self.parser._ensure_connected = unittest.mock.AsyncMock(side_effect=connect)
        self.assertFalse(
            await self.parser._execute_command_safely(
                self.hass,
                self.device,
                {"Type": "Change"},
                request={"result_future": future},
            )
        )
        self.assertEqual(tracker.events, [])

    async def test_expiry_during_adaptive_delay_never_submits_setting(self):
        await self.parser._ensure_connected(self.hass, self.device)
        self.parser._get_operation_delay = lambda *args: 0.05
        future = asyncio.get_running_loop().create_future()
        task = asyncio.create_task(
            self.parser._execute_command_safely(
                self.hass,
                self.device,
                {"Type": "Change"},
                request={"result_future": future},
            )
        )
        await asyncio.sleep(0.01)
        future.cancel()
        self.assertFalse(await task)
        self.assertEqual([e[0] for e in tracker.events], ["auth"])

    async def test_unconfirmed_disconnect_retains_client_reference(self):
        await self.parser._ensure_connected(self.hass, self.device)
        client = self.parser._client
        original = client.disconnect
        client.disconnect = unittest.mock.AsyncMock()
        with self.assertRaises(BleakError):
            await self.parser._disconnect_safely()
        self.assertIs(self.parser._client, client)
        self.assertTrue(client.is_connected)
        client.disconnect = original

    async def test_callback_cancellation_does_not_release_another_task_lock(self):
        async with self.parser._client_operation():
            task = asyncio.create_task(
                self.parser._ensure_connected(self.hass, self.device)
            )
            await asyncio.sleep(0)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertIs(self.parser._client_lock_owner, asyncio.current_task())
        self.assertFalse(self.parser._client_lock.locked())
        self.assertEqual(tracker.events, [])


if __name__ == "__main__":
    unittest.main()
