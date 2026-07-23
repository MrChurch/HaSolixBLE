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

## Differential captures 19-21

The three isolated app captures provide a useful command-level separation:

* Capture 19 (light on/off) does not add a new command family beyond the
  normal session traffic.
* Capture 20 (repeated firmware-list requests) increases `4030`/`4830` and
  contains additional `4840` responses. `4030` is therefore the current
  firmware-query candidate.
* Capture 21 (AC emergency outlet on/off) increases `4073`/`4873` only.
  `4073` is therefore the current AC-OUT/Notstromsteckdose candidate.

This is a differential identification of command families, not a value
mapping: all application payloads are still protected by the dynamic SB3
session encryption.

## APK 3.8.0 static cross-check

The supplied Flutter APK contains compiled A17C5-related symbols for the
same functional areas:

* lighting: `setLocationLightSwitchCmd`, `setLcdLight`,
  `setAmbientLightSwitch`, `setDeviceLightMode`, `setDevicePullLightTime`,
  `setLightAndSOSCmd`, `setLightState`, `setLightness` and `setLightnessSwitch`;
* AC output: `setAcOutput`, `setAcOutputMode`, `setAcOutputSmartMode`,
  `acOutputCountDownEnable` and `acOutputState`;
* firmware: `firmwareVersion`, `firmwareBattery`, `checkFirmware` and
  `firmwareUpdateRequest`.

This confirms that the UI has separate controls for lighting, AC output and
firmware information. The APK is Flutter AOT (`lib/arm64-v8a/libapp.so`), so
the numeric BLE command values and encrypted field layouts are not present as
readable source strings. Static APK inspection therefore confirms the
feature surface, but does not by itself prove which function owns a specific
encrypted command payload.

## Decrypted firmware response

The authenticated `4030` -> `4830` exchange has since been decoded from the
matching session transcript. Its compact TLVs report:

* `A1`: internal MCU firmware `v0.3.3.0`;
* `A2`: primary Solarbank firmware `v1.0.7.1`;
* `A3`: model `A17C5`;
* `A4`/`A5`: `A17C5_mcu` and `A17C5_esp32` component identifiers.

The integration now requests this read-only response after session setup and
exposes it through the Solarbank 3 **Firmware Versions** sensor. Battery
firmware strings are extracted from decrypted `4409` metadata only when the
device actually includes them; the three `v0.3.5.5` values reported by the
app have not been treated as independently proven BLE fields yet.
