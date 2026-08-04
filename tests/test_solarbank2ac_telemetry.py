"""Solarbank 2 E1600 AC A17C0 telemetry tests."""

import struct

from custom_components.solix_ble.SolixBLE.devices.solarbank2 import Solarbank2AC


def _typed_float(value: float) -> bytes:
    """Build one A17C0 typed float32 telemetry value."""
    return b"\x05" + struct.pack("<f", value)


def test_sb2ac_preserves_unlabelled_typed_float_candidates() -> None:
    """A17C0 candidates must not use legacy Solarbank 2 integer divisors."""
    device = object.__new__(Solarbank2AC)
    device._data = {
        "b0": _typed_float(975.8707),
        "b1": _typed_float(66.2857),
        "c4": _typed_float(-231.0),
    }

    assert device.sb2ac_telemetry_candidates == {
        "b0": 975.8707275390625,
        "b1": 66.28569793701172,
        "c4": -231.0,
    }
    assert device.power_out == -1
    assert device.grid_import_power == -1

    device._data["ad"] = _typed_float(151.0)
    device._data["d7"] = _typed_float(231.0)
    device._data["a5"] = b"\x01\x25"
    device._data["a4"] = b"\x01\x01"
    device._data["b5"] = b"\x01\x0a"
    device._data["b7"] = b"\x01\x5f"
    device._data["bd"] = b"\x02\x5e\x01"
    device._data["c5"] = _typed_float(150.0)
    device._schedule_power_target = 0
    device._schedule_power_target_staged = False
    device._max_load_target = 800
    device._max_load_target_staged = False
    assert device.power_out == 151
    assert device.grid_import_power == 231
    assert device.temperature == 37
    assert device.discharge_limit == 10
    assert device.charge_limit == 95
    assert device.usage_mode == "Custom"
    assert device.max_load_limit == 350
    assert device.sync_schedule_power_target() == 150
    assert device.schedule_power_target == 150
    assert device.sync_max_load_target() == 350
    assert device.max_load_target == 350

    device.set_schedule_power_target(300)
    assert device.schedule_power_target == 300
    device.set_max_load_target(600)
    assert device.max_load_target == 600

    device._data["a4"] = b"\x01\x00"
    assert device.usage_mode == "Self consumption"
