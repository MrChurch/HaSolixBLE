# Home Assistant Solix BLE

Home Assistant integration for monitoring and controlling Anker Solix devices
over a local Bluetooth connection.

This repository is the actively tested fork:

<https://github.com/MrChurch/HaSolixBLE>

!!! ORIGINAL CODE: https://github.com/flip-dots/HaSolixBLE !!!
!!! ORIGINAL CODE: https://github.com/flip-dots/HaSolixBLE !!!
!!! ORIGINAL CODE: https://github.com/flip-dots/HaSolixBLE !!!

## Features

- Battery percentage, health and temperature
- Total power in/out
- Solar input and PV yield
- Individual PV input ports
- AC/DC and USB monitoring for supported devices
- Firmware and device information
- Local BLE session authentication and encrypted telemetry

## Solarbank 3 E2700 Pro (A17C5)

Solarbank 3 support was initially tested with an A17C5 reporting primary
firmware `v1.0.7.1` and internal MCU firmware `v0.3.3.0`. It has also been
adapted for Solarbank firmware `v1.0.7.3`: its `4409` battery metadata uses a
new record marker while retaining the existing serial number, temperature and
state-of-charge layout.
The integration establishes the authenticated local BLE session using the
device's ECDH key exchange, negotiated AES-GCM session key and MAC validation.
No cloud account or firmware modification is required.

### Solarbank 2 AC

Solarbank 2 E1600 AC (A17C0) is available as a separate model selection. It
does **not** reuse the legacy Solarbank 2 sensor decoder: its encrypted `c405`
telemetry contains typed values with a different layout. Applying the legacy
integer/divisor mapping produces physically impossible readings, so the AC
variant is intentionally kept in its own device class.

Validated local telemetry currently exposed for the AC model:

- battery percentage and average battery percentage (the AC has no expansion
  battery telemetry, so both represent the unit SOC)
- charge and discharge limits
- temperature, serial number, Total Power Out and Grid Import Power
- read-only Usage mode (`Custom` or `Self consumption`)
- Solar Power In and PV ports 1/2, decoded from the observed typed A17C0 tags
  `ab`, `c6` and `c7`

The local controls are an all-day Custom schedule (`405e`, 0-800 W in 50 W
steps) and the staged maximum load limit (`4080`). The usage-mode value is
telemetry only. An earlier experimental local mode setter did not reproduce
the Anker app behaviour and has deliberately been removed.

Unassigned legacy sensors (energy counters, AC socket power, heater status,
firmware fields, grid status and similar values) are disabled for Solarbank 2
AC instead of displaying guessed or stale data. Existing installations are
cleaned up automatically when the integration is reloaded.

#### Continuing the A17C0 decoder

Please capture one app action at a time and retain the matching BLE log. Good
next candidates are PV input under real PV generation, energy counters and
the app-side mode change. A new field should only be published after its raw
typed value has been correlated with a controlled change and backed by a
regression test. Do not copy Solarbank 2 or Solarbank 3 field offsets into the
AC model without that verification.

### Telemetry

The following Solarbank 3 values are decoded from the encrypted `c405`
telemetry response:

- **Total Power Out** – live inverter output (`ad`)
- **Total Power In** – active battery charging power (`bc`)
- **Schedule power** – active charge/discharge schedule target (`b9`)
- **PV Max** – PV maximum limit (`d5`)
- Solar Power In (`ab`)
- PV Yield (`ac`)
- Solar Power In Port 1–4 (`c7`–`ca`)
- Battery, grid and household power values

### Firmware information

After authentication the integration performs the read-only `4030` firmware
query. The authenticated `4830` response is decoded into the **Firmware
Versions** sensor. On the tested A17C5 it reports the primary Solarbank
firmware (`v1.0.7.1`), the internal MCU firmware (`v0.3.3.0`) and the MCU/
ESP32 component identifiers. Solarbank firmware `v1.0.7.3` changes the `4409`
battery-record marker from `63 01` to `6A 01`; both layouts are supported.
Battery firmware versions are appended when they are present in the decrypted
`4409` metadata; no value is guessed from the Anker app display.

### Local controls

The Solarbank 3 device page provides staged controls and explicit apply
buttons:

- **Schedule power target**: 0–1200 W in 50 W steps; writes the seven-day
  `405e` schedule command.
- **Schedule mode**: implemented and verified for both `discharge` and
  `charge`. Select the direction in the dropdown, set the positive power
  target, then press **Apply schedule**. The direction is encoded in each
  schedule slot; power values are never negative.
- **Maximum load limit**: 350, 600, 800 or 1200 W; writes the `4080` command.

The charge/discharge mode and power target are sent together over the local
BLE connection. The device therefore changes its active behavior immediately;
the plan description/value shown in the Anker app is cloud-backed metadata and
may still show the previous value.

The active device value changes immediately over BLE and is visible in the
telemetry.

> **BLE control resolution:** Solarbank 3 local BLE schedule writes use the
> captured and validated 50 W increment (0-1200 W). This is intentionally
> enforced by the integration. The Anker app's Wi-Fi/cloud control may offer
> 10 W increments; that is a different control path and is not assumed to be
> valid for the local BLE command.

## Supported devices

The integration supports the following devices and variants:

- C300(X) and C300(X) DC
- C800(X)
- C1000(X) and C1000(X) Gen 2
- F2000
- F3800
- Anker Prime 160 W Charger
- Anker Prime 250 W Charger
- Anker Prime 20k (220 W) Power Bank
- Solarbank 2
- Solarbank 2 E1600 AC (A17C0)
- Solarbank 3 E2700 Pro (A17C5)

## Installation (HACS)

1. Ensure [HACS](https://www.hacs.xyz/) is installed.
2. Add `https://github.com/MrChurch/HaSolixBLE` as a custom repository.
3. Install the integration and restart Home Assistant.

## Setup

1. Enable Bluetooth pairing on the device (the Bluetooth indicator should
   blink).
2. Open the Home Assistant device page and add the detected power station.
3. Select the matching device model.
4. Confirm and wait for the authenticated BLE session to complete.

For Bluetooth proxies, make sure the proxy can reach the device reliably and
that no other client is holding the Solarbank connection during setup.

## Limitations

- Bluetooth and Wi-Fi cannot be used simultaneously on some device models.
- Solarbank 3 plan metadata in the Anker app remains cloud-managed; local BLE
  changes affect the device and telemetry, not the app's cached plan entry.
- This project is not affiliated with Anker Innovations Limited.

## Adding support for new devices

Enable debug logging for an unsupported device and compare the raw telemetry
and parameter differences while changing one device setting at a time. The
underlying BLE protocol and payload parser can then be extended with a focused
mapping and regression test.

## Disclaimer

Home Assistant Solix BLE is an unofficial software project for locally owned
Anker Solix/Prime devices. ANKER is a registered trademark of Anker Innovations
Limited. No firmware is modified and no cloud or security mechanism is
bypassed.
