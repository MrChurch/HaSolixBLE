# BLE protocol evidence

This directory contains local protocol evidence for the Solarbank 3 BLE
reverse-engineering work. Binary Bluetooth HCI captures are kept under
`logs/ble-captures/`; text exports and decrypted Home Assistant traces remain
available alongside the earlier captures.

The captures are evidence only. They are not loaded by the integration at
runtime and must not be treated as configuration. Device addresses, serial
numbers and encrypted packets may be present in the files, so they should not
be published outside this project without review.

When a new BLE capture or protocol trace is attached in the conversation, copy
the original file into `logs/ble-captures/` using its original filename and
record its capture context in the conversation (device, firmware, action and
timestamp). Existing files are de-duplicated by SHA-256 before copying.

`copy-manifest.csv` records the SHA-256 and byte size of the files imported in
the current archive pass.

## `btsnoop_hci (17).log`

This capture covers a Solarbank 3 with three connected expansion batteries
(one BP1600 and two BP2700) and two AC emergency-outlet toggles. The encrypted
`4409` telemetry metadata occurs with both 141-byte and 193-byte protocol
payloads; the larger payload is consistent with the additional battery record.
The HCI capture does not contain the session key, so the battery serials,
capacity/type byte, firmware versions, and the plaintext AC-out command fields
cannot be decoded from this file alone. A matching Home Assistant debug trace
from the same run is required for those mappings.

## `btsnoop_hci (18).log`

This follow-up capture contains the requested light, timeout, SOC-limit,
MPPT-limit, AC-input-limit and firmware-list interactions. The command
inventory adds repeated `4067`, `4068` and `409a` exchanges (with `4867`,
`4868` and `489a` replies), while the already observed light candidates
`4030`/`4073` are present again. The capture also contains 193-byte `4409`
metadata packets, consistent with three expansion-battery records.

The HCI payloads remain session-encrypted. Therefore the command IDs can be
correlated with the UI actions, but their state/value fields must not be
implemented until a matching decrypted HA trace or a controlled live test
confirms the payload layout.
