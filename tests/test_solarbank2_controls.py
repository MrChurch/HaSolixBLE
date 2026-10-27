"""Solarbank 2 AC local-control payload tests."""

import pytest

from custom_components.solix_ble.SolixBLE.devices.solarbank2 import (
    MaxLoadSB2,
    Solarbank2,
    Solarbank2AC,
)


def test_sb2_schedule_uses_ten_watt_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    """The direct builder must match the 10 W Home Assistant control step."""
    monkeypatch.setattr("os.urandom", lambda size: b"\x01" * size)

    payload = Solarbank2._build_set_schedule_payload(400)

    assert payload[18:20] == bytes.fromhex("9001")
    assert payload[-7:] == bytes.fromhex("fd050301010101")


@pytest.mark.parametrize("power_w", (-10, 1, 405, 810))
def test_sb2_schedule_rejects_unsupported_direct_targets(power_w: int) -> None:
    """Direct writes cannot bypass the captured 0--800 W / 10 W constraint."""
    with pytest.raises(ValueError, match="10 W steps"):
        Solarbank2._build_set_schedule_payload(power_w)


def test_sb2_max_load_payload_keeps_little_endian_limit() -> None:
    """The inherited SB2 AC 4080 command retains its captured wire layout."""
    assert Solarbank2._build_set_max_load_payload(MaxLoadSB2.W800) == bytes.fromhex(
        "a10121a203022003a303020000"
    )


def test_sb2ac_supports_1200_w_discharge_schedule() -> None:
    """The AC model has a higher verified custom-plan discharge ceiling."""
    payload = Solarbank2AC._build_set_schedule_payload(1200)

    assert payload[18:20] == bytes.fromhex("b004")


def test_sb2ac_max_load_supports_1200_w() -> None:
    """The A17C0 on-grid maximum-load selector includes its 1200 W option."""
    assert Solarbank2._build_set_max_load_payload(MaxLoadSB2.W1200) == bytes.fromhex(
        "a10121a20302b004a303020000"
    )
