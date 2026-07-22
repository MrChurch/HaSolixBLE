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

Solarbank 3 support has been tested with an A17C5 running firmware 0.3.3.0.
The integration establishes the authenticated local BLE session using the
device's ECDH key exchange, negotiated AES-GCM session key and MAC validation.
No cloud account or firmware modification is required.

### Telemetry

The following Solarbank 3 values are decoded from the encrypted `c405`
telemetry response:

- **Total Power Out** – live inverter output (`ad`)
- **Schedule output power** – active schedule target (`b9`)
- **PV Max** – PV maximum limit (`d5`)
- Solar Power In (`ab`)
- PV Yield (`ac`)
- Solar Power In Port 1–4 (`c7`–`ca`)
- Battery, grid and household power values

### Local controls

The Solarbank 3 device page provides staged controls and explicit apply
buttons:

- **Schedule power target**: 0–1200 W in 50 W steps; writes the seven-day
  `405e` schedule command.
- **Schedule mode**: `discharge` or `charge`; the selected direction is encoded
  in each schedule slot and is applied together with the target power.
- **Maximum load limit**: 350, 600, 800 or 1200 W; writes the `4080` command.

The active device value changes immediately over BLE and is visible in the
telemetry. The plan description/value shown in the Anker app is cloud-backed
metadata and is not rewritten by the local BLE command; the app may therefore
continue to display the previous plan value even though the Solarbank is
operating at the new target.

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
