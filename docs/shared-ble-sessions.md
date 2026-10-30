# Short BLE sessions

MicroAir acquires a BLE lease for each authenticated status read, command and zone-capability probe, then disconnects before releasing it. The default status interval remains 30 seconds. Zone values and capability caches survive intentional disconnects. Commands retain FIFO order and precede pending routine polls; after three controls a waiting poll gets a turn. Expired commands are dropped before their first setting write. Once submitted, a command finishes its bounded verification transaction.

## Optional coordination contract, version 1

The integration works by itself. Other integrations can opt into the same per-Home-Assistant connection budget without importing MicroAir by using the compatible broker API under `hass.data["shared_ble_session_broker_v1"]`. The first integration constructs the broker; all subsequent integrations reuse it with `setdefault`.

A participant implements `_ensure_connected()`, `_cleanup_connection()`, `_finish_ble_session()` and `_logger`. Its stable participant object is passed to `broker.session(participant, poll=True|False)`. Session ownership is identified by the current asyncio task, so only nested calls in that same task/participant are reentrant. Callback tasks acquire independently. `broker.owned_by(participant)` tests ownership. Queue wait is outside the acquired-session timeout: 15 seconds for routine polls and 45 for controls. Participants must bound cleanup themselves; MicroAir allows five seconds and retains an unconfirmed connected client so the broker blocks new connections until cleanup succeeds.

The contract governs only participants that opt in, not all Bluetooth integrations. A copied broker implementation must retain this API, ordering, cleanup and ownership behavior. A breaking change requires another versioned key; do not silently reuse the v1 key with incompatible behavior.

Run the self-contained mocked tests with `python -m unittest discover -s tests -v`. They execute complete production parser classes and the broker, including independent participant/load-order checks. No Home Assistant installation or real BLE hardware is required for these tests.
