"""Solarbank 3 PV telemetry tests."""

import struct

from custom_components.solix_ble.SolixBLE.devices.solarbank3 import Solarbank3


def _float_tlv(value: float) -> bytes:
    """Build the typed float value used by SB3 telemetry."""
    return bytes([0x05]) + struct.pack("<f", value)


def _device_with_pv_values(total: float, port_1: float, port_2: float,
                           port_3: float, port_4: float) -> Solarbank3:
    device = Solarbank3.__new__(Solarbank3)
    device._data = {
        "ab": _float_tlv(total),
        "c7": _float_tlv(port_1),
        "c8": _float_tlv(port_2),
        "c9": _float_tlv(port_3),
        "ca": _float_tlv(port_4),
    }
    return device


def test_sb3_port_2_recovers_missing_pv_from_total() -> None:
    device = _device_with_pv_values(689, 309, 23, 13, 40)

    assert device.solar_pv_2_power_in == 327


def test_sb3_port_2_keeps_raw_value_when_values_match() -> None:
    device = _device_with_pv_values(385, 309, 23, 13, 40)

    assert device.solar_pv_2_power_in == 23


def test_sb3_clears_stale_port_value_when_total_pv_is_zero() -> None:
    device = _device_with_pv_values(0, 0, 0, 0, 40)

    assert device.solar_power_in == 0
    assert device.solar_pv_4_power_in == 0
