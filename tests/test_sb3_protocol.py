"""Protocol-level tests for the Solarbank 3 secure session flow."""

from cryptography.hazmat.primitives.asymmetric import ec

from custom_components.solix_ble.SolixBLE.sb3_protocol import (
    SB3_DEFAULT_CLIENT_ID,
    SB3State,
    aes_gcm_decrypt,
    build_packet,
    build_security_auth_packet,
    build_security_auth_plaintext,
    build_sb3_schedule_plaintext,
    build_telemetry_request_plaintext,
    parse_packet,
)


def test_4027_is_session_encrypted_and_contains_fresh_timestamp() -> None:
    """4027 must use the established AES-GCM key, not the initial key."""
    key = bytes(range(16))
    nonce = bytes(range(12))
    packet = build_security_auth_packet(key, nonce, timestamp=1_700_000_000)

    parsed = parse_packet(packet)
    assert parsed.pattern == bytes.fromhex("030001")
    assert parsed.command == bytes.fromhex("4027")
    assert aes_gcm_decrypt(key, nonce, parsed.payload) == build_security_auth_plaintext(
        SB3_DEFAULT_CLIENT_ID, 1_700_000_000
    )


def test_authenticated_4827_marks_session_ready_and_returns_4040() -> None:
    """A valid 4827 is the only transition which enables telemetry."""
    from custom_components.solix_ble.SolixBLE.sb3_protocol import SB3Handshake

    handshake = SB3Handshake("A17C5", "00:11:22:33:44:55")
    handshake.state = SB3State.WAIT_4827
    handshake.session_key = bytes(range(16))
    handshake.session_nonce = bytes(range(12))
    response = build_packet(
        bytes.fromhex("030001"),
        bytes.fromhex("4827"),
        # An authenticated acknowledgement may carry implementation-specific
        # fields; the GCM verification, not a guessed fixed payload, is binding.
        __import__("custom_components.solix_ble.SolixBLE.sb3_protocol", fromlist=["aes_gcm_encrypt"]).aes_gcm_encrypt(
            handshake.session_key, handshake.session_nonce, b"\x04"
        ),
    )

    next_packet = handshake.receive(response)

    assert handshake.session_ready
    assert parse_packet(next_packet).command == bytes.fromhex("4040")
    assert aes_gcm_decrypt(
        handshake.session_key,
        handshake.session_nonce,
        parse_packet(next_packet).payload,
    ).startswith(
        bytes.fromhex("a10121fe0503")
    )


def test_4040_status_query_uses_solix_timestamp_tlv() -> None:
    """4040 uses the captured Solix replay-protection timestamp TLV."""
    assert build_telemetry_request_plaintext(1_700_000_000) == bytes.fromhex(
        "a10121fe050300f15365"
    )


def test_sb3_schedule_matches_captured_405e_layout() -> None:
    """A 405e schedule has seven 22-byte weekday blocks and fd token."""
    first = build_sb3_schedule_plaintext(350, fd_token=b"\x01\x02\x03\x04")
    second = build_sb3_schedule_plaintext(400, fd_token=b"\x01\x02\x03\x04")

    assert len(first) == 168
    assert first[:7] == bytes.fromhex("a10121a2020101")
    assert first[161:] == bytes.fromhex("fd050301020304")
    assert [first[18 + 22 * day] for day in range(7)] == [0x5E] * 7
    assert [second[18 + 22 * day] for day in range(7)] == [0x90] * 7
    assert [a ^ b for a, b in zip(first, second)] == [
        0xCE if index in {18 + 22 * day for day in range(7)} else 0
        for index in range(len(first))
    ]
