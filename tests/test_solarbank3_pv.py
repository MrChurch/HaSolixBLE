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
        "c6": _float_tlv(port_1),
        "c7": _float_tlv(port_2),
        "c8": _float_tlv(port_3),
        "c9": _float_tlv(port_4),
    }
    return device


def test_sb3_maps_four_pv_ports_to_c6_through_c9() -> None:
    device = _device_with_pv_values(689, 309, 23, 13, 40)

    assert device.solar_pv_1_power_in == 309
    assert device.solar_pv_2_power_in == 23
    assert device.solar_pv_3_power_in == 13
    assert device.solar_pv_4_power_in == 40


def test_sb3_port_2_keeps_raw_value_when_values_match() -> None:
    device = _device_with_pv_values(385, 309, 23, 13, 40)

    assert device.solar_pv_2_power_in == 23


def test_sb3_clears_stale_port_value_when_total_pv_is_zero() -> None:
    device = _device_with_pv_values(0, 0, 0, 0, 40)

    assert device.solar_power_in == 0
    assert device.solar_pv_4_power_in == 0


def test_sb3_keeps_total_and_ports_consistent() -> None:
    device = _device_with_pv_values(1150, 706, 340, 64, 40)

    assert device.solar_pv_4_power_in == 40
    assert device.solar_power_in == 1150
    assert sum(
        (
            device.solar_pv_1_power_in,
            device.solar_pv_2_power_in,
            device.solar_pv_3_power_in,
            device.solar_pv_4_power_in,
        )
    ) == 1150


def test_sb3_does_not_use_fixed_ca_as_pv_port() -> None:
    device = _device_with_pv_values(408, 0, 246, 101, 40)

    assert device.solar_power_in == 408
    assert device.solar_pv_2_power_in == 246
    assert device.solar_pv_4_power_in == 40


def test_sb3_average_battery_percentage_includes_expansion_battery() -> None:
    """Aggregate SOC averages the main and inserted battery percentages."""
    device = Solarbank3.__new__(Solarbank3)
    device._is_solarbank3_transport = True
    device._data = {"a3": bytes((0x01, 77))}
    device._sb3_battery_metadata = (
        b"APCDJQD0F1440094"
        + bytes((0x63, 0x01, 0x02, 28, 0x02, 88, 0x64))
    )

    assert device.battery_percentage == 77
    assert device.expansion_battery_1_percentage == 88
    assert device.battery_percentage_aggregate == 82.0


def test_sb3_schedule_target_syncs_from_live_device_value() -> None:
    """The HA slider starts at the active device schedule, not zero."""
    device = Solarbank3.__new__(Solarbank3)
    device._data = {"b9": bytes.fromhex("022c01")}
    device._schedule_power_target = 0
    device._schedule_power_target_staged = False

    assert device.sync_schedule_power_target() == 300
    assert device.schedule_power_target == 300


def test_sb3_total_power_in_uses_charge_telemetry() -> None:
    """The charge capture's ``bc`` field exposes total input power."""
    device = Solarbank3.__new__(Solarbank3)
    device._data = {"bc": _float_tlv(300)}

    assert device.power_in == 300
