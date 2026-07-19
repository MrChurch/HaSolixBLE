"""Windows-compatible unit tests for Solarbank 3 device payload handling."""

import sys
from importlib import import_module
from pathlib import Path
from types import ModuleType

# Load the bundled SolixBLE folder as an isolated package. This avoids both the
# Home Assistant parent package and a collision between its select.py and the
# Python standard-library module with the same name.
PACKAGE_NAME = "_local_solix_ble"
PACKAGE_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "solix_ble"
    / "SolixBLE"
)
package = ModuleType(PACKAGE_NAME)
package.__path__ = [str(PACKAGE_PATH)]
sys.modules[PACKAGE_NAME] = package
device_module = import_module(f"{PACKAGE_NAME}.device")

_is_complete_sb3_tlv_payload = device_module._is_complete_sb3_tlv_payload
_is_sb3_command_acknowledgement = device_module._is_sb3_command_acknowledgement


def test_sb3_command_acknowledgement_matches_observed_payload() -> None:
    """The short 405e/4080 response must not be parsed as telemetry TLVs."""
    assert _is_sb3_command_acknowledgement(bytes.fromhex("01a10131"))


def test_sb3_command_acknowledgement_rejects_similar_payloads() -> None:
    """Only the complete observed four-byte acknowledgement is accepted."""
    assert not _is_sb3_command_acknowledgement(bytes.fromhex("01a101"))
    assert not _is_sb3_command_acknowledgement(bytes.fromhex("01a1013100"))
    assert not _is_sb3_command_acknowledgement(bytes.fromhex("01a10231"))


def test_sb3_tlv_validation_accepts_complete_payloads() -> None:
    """Complete telemetry parameters may include the observed leading zero."""
    assert _is_complete_sb3_tlv_payload(bytes.fromhex("a10131"))
    assert _is_complete_sb3_tlv_payload(bytes.fromhex("00a10131b9029600"))


def test_sb3_tlv_validation_rejects_empty_or_truncated_payloads() -> None:
    """Malformed authenticated responses must be filtered before TLV parsing."""
    assert not _is_complete_sb3_tlv_payload(b"")
    assert not _is_complete_sb3_tlv_payload(b"\x00")
    assert not _is_complete_sb3_tlv_payload(bytes.fromhex("a1"))
    assert not _is_complete_sb3_tlv_payload(bytes.fromhex("01a10131"))
    assert not _is_complete_sb3_tlv_payload(bytes.fromhex("00b90296"))
