"""Solarbank 3 PV telemetry tests."""

import asyncio
import struct

from custom_components.solix_ble.SolixBLE.devices.solarbank3 import Solarbank3
from custom_components.solix_ble.SolixBLE.device import _parse_sb3_firmware_payload


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


def test_sb3_new_firmware_uses_6a_battery_metadata_marker() -> None:
    """Newer SB3 firmware changes only the metadata marker prefix."""
    device = Solarbank3.__new__(Solarbank3)
    device._sb3_battery_metadata = (
        b"APCDJF4G72230095"
        + bytes((0x6A, 0x01, 0x02, 25, 0x02, 80, 0x64))
    )

    assert device.expansion_battery_1_serial_number == "APCDJF4G72230095"
    assert device.expansion_battery_1_temperature == 25
    assert device.expansion_battery_1_percentage == 80


def test_sb3_single_payload_starting_with_11_is_not_a_fragment() -> None:
    """A one-part 4409 blob may legitimately start with ciphertext byte 0x11."""
    device = Solarbank3.__new__(Solarbank3)
    payload = b"\x11" + b"x" * 182
    device._sb3_raw_packets = {}
    device._sb3_raw_fragments = {}
    device._sb3_handshake = None

    asyncio.run(
        device._process_sb3_raw_telemetry(
            b"\x03\x01\x0f", b"\x44\x09", payload,
        ),
    )

    assert device._sb3_raw_packets["4409"] == payload
    assert device._sb3_raw_fragments == {}


def test_sb3_two_part_payload_still_reassembles_fragments() -> None:
    """Keep the verified 0x12/0x22 transport framing intact."""
    device = Solarbank3.__new__(Solarbank3)
    device._sb3_raw_packets = {}
    device._sb3_raw_fragments = {}
    device._sb3_handshake = None

    asyncio.run(
        device._process_sb3_raw_telemetry(
            b"\x03\x01\x0f", b"\xc4\x05", b"\x12first",
        ),
    )
    asyncio.run(
        device._process_sb3_raw_telemetry(
            b"\x03\x01\x0f", b"\xc4\x05", b"\x22second",
        ),
    )

    assert device._sb3_raw_packets["c405"] == b"firstsecond"
    assert device._sb3_raw_fragments == {}


def test_sb3_reconnect_timeout_keeps_last_verified_battery_topology() -> None:
    """A reconnect timeout must not erase expansion entities permanently."""
    device = Solarbank3.__new__(Solarbank3)
    metadata = b"APCDJF4G72230095" + bytes((0x6A, 0x01, 0x02, 25, 0x02, 80, 0x64))
    device._data = {"a3": bytes((0x01, 77))}
    device._last_data_timestamp = object()
    device._fragment_buffers = {}
    device._fragment_totals = {}
    device._shared_secret = b"old-session"
    device._sb3_session_ready = True
    device._sb3_schedule_telemetry_ready = True
    device._sb3_identity_authenticated = True
    device._sb3_raw_packets = {"4409": metadata}
    device._sb3_battery_metadata = metadata
    device._sb3_firmware_metadata = {"a2": "v1.0.7.1"}
    device._sb3_battery_firmware_versions = ("v0.3.5.5",)
    device._sb3_raw_fragments = {}
    device._sb3_handshake = object()
    device._sb3_checkpoint_complete = True
    device._sb3_transcript_path = "/tmp/transcript.json"
    device._sb2ac_session_ready = False
    device._sb2ac_raw_packets = {}
    device._sb2ac_raw_fragments = {}
    device._sb2ac_handshake = None
    device._last_packet_timestamp = 1.0
    device._negotiation_timestamp = 2.0
    device._last_negotiation_request_timestamp = 3.0
    device._command_characteristic = object()
    device._telemetry_characteristic = object()
    device._packet_futures = {}

    device._reset_session(
        reset_data=True,
        preserve_sb3_battery_metadata=True,
    )

    assert device._data is None
    assert device._sb3_schedule_telemetry_ready is False
    assert device._sb3_battery_metadata == metadata
    assert device.expansion_battery_1_percentage == 80
    assert device._sb3_firmware_metadata == {"a2": "v1.0.7.1"}


def test_sb3_schedule_target_syncs_from_live_device_value() -> None:
    """The HA slider starts at the active device schedule, not zero."""
    device = Solarbank3.__new__(Solarbank3)
    device._data = {"b9": bytes.fromhex("022c01")}
    device._schedule_power_target = 0
    device._schedule_power_target_staged = False
    device._sb3_schedule_telemetry_ready = True

    assert device.sync_schedule_power_target() == 300
    assert device.schedule_power_target == 300


def test_sb3_pv_max_target_syncs_from_live_d5_value() -> None:
    """The MPPT selector follows only verified 2000/3600 W telemetry."""
    device = Solarbank3.__new__(Solarbank3)
    device._data = {"d5": bytes.fromhex("02d007")}
    device._pv_max_target = 3600
    device._pv_max_target_staged = False

    assert device.sync_pv_max_target() == 2000
    assert device.pv_max_target == 2000


def test_sb3_cached_schedule_is_not_used_before_current_session_refresh() -> None:
    """A power-cycle must not make an old HA slider value writeable."""
    device = Solarbank3.__new__(Solarbank3)
    device._data = {"b9": bytes.fromhex("022c01")}
    device._schedule_power_target = 450
    device._schedule_power_target_staged = False
    device._sb3_schedule_telemetry_ready = False

    assert device.sync_schedule_power_target() is None
    assert device.schedule_power_target == 450


def test_sb3_rejects_schedule_write_before_current_session_refresh() -> None:
    """405e is fail-safe until fresh ``b9`` telemetry arrives."""
    device = Solarbank3.__new__(Solarbank3)
    device._sb3_schedule_telemetry_ready = False

    try:
        asyncio.run(device.set_schedule(300))
    except ConnectionError as error:
        assert "not been refreshed" in str(error)
    else:
        raise AssertionError("schedule write unexpectedly accepted")


def test_sb3_recreates_full_day_schedule_without_b9_telemetry() -> None:
    """The manual recovery path restores a seven-day plan after a power cycle."""
    device = Solarbank3.__new__(Solarbank3)
    device._sb3_schedule_telemetry_ready = False
    device._schedule_mode = "discharge"
    device._schedule_power_target = 200
    device._schedule_power_target_staged = True
    sent: list[tuple[bytes, bytes]] = []

    async def send(command: bytes, payload: bytes) -> None:
        sent.append((command, payload))

    device._send_sb3_command = send

    asyncio.run(device.recreate_full_day_schedule(300))

    assert sent[0][0] == bytes.fromhex("405e")
    assert len(sent[0][1]) == 168
    assert device._schedule_power_target == 300
    assert device._schedule_power_target_staged is False


def test_sb3_total_power_in_uses_charge_telemetry() -> None:
    """The charge capture's ``bc`` field exposes total input power."""
    device = Solarbank3.__new__(Solarbank3)
    device._data = {"bc": _float_tlv(300)}

    assert device.power_in == 300


def test_sb3_firmware_sensor_lists_bank_and_detected_battery_versions() -> None:
    """The display value keeps the proven bank fields and decoded batteries."""
    device = Solarbank3.__new__(Solarbank3)
    device._is_solarbank3_transport = True
    device._sb3_firmware_metadata = {
        "a1": "v0.3.3.0",
        "a2": "v1.0.7.1",
        "a3": "A17C5",
        "a4": "A17C5_mcu",
        "a5": "A17C5_esp32",
    }
    device._sb3_battery_firmware_versions = ("v0.3.5.5",) * 3

    assert device.software_version == "v1.0.7.1"
    assert device.firmware_versions == (
        "Solarbank: v1.0.7.1 | Internal MCU: v0.3.3.0 | "
        "MCU component: A17C5_mcu | ESP32 component: A17C5_esp32 | "
        "Battery 1: v0.3.5.5 | Battery 2: v0.3.5.5 | "
        "Battery 3: v0.3.5.5"
    )


def test_sb3_firmware_response_decodes_authenticated_ascii_tlvs() -> None:
    """The 4830 response maps A1-A5 without using telemetry offsets."""
    payload = (
        b"\x04\xa1\x08v0.3.3.0\xa2\x08v1.0.7.1\xa3\x05A17C5"
        b"\xa4\x09A17C5_mcu\xa5\x0bA17C5_esp32"
    )

    assert _parse_sb3_firmware_payload(payload) == {
        "a1": "v0.3.3.0",
        "a2": "v1.0.7.1",
        "a3": "A17C5",
        "a4": "A17C5_mcu",
        "a5": "A17C5_esp32",
    }
