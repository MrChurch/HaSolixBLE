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
