# Persistent per-parser operations

The parser retains its original persistent BLE connection, authentication, polling interval and idle/health policy. Its existing client lock now supports reentrancy only within the owning asyncio task, so complete command/verification sequences, polls, startup/configuration probes and cleanup cannot modify the same client concurrently. Separate parser instances operate independently. Home Assistant/Bleak retain adapter, connection-slot and retry handling; no global queue or cross-integration broker is introduced.

FIFO commands that expire before their first setting write are discarded, including after waiting on the client lock, connection setup or an adaptive delay. Once a setting write starts, its verification sequence continues. Reconnect confirms old-client cleanup before replacing the reference. A failed disconnect retains an unconfirmed client reference instead of silently abandoning it. Runtime zone-configuration refresh reuses the authenticated persistent client and preserves both zones/capability caches.

This does not free persistent proxy slots or validate an optional disconnect-after-operation policy. Such a capability requires exact protocol/model evidence and separate hardware tests.

Run `python -m unittest discover -s tests -v` for self-contained tests executing the complete production parser classes with fake BLE. Tests cover repeated polls with one authentication, both zones, atomic control/verification, independent devices, command expiry, cancellation and cleanup reference safety. This revised lifecycle has not been deployed or validated on hardware.
