"""Solarbank 2 AC dynamic-handshake tests."""

from cryptography.hazmat.primitives.asymmetric import ec

from custom_components.solix_ble.SolixBLE.sb2ac_protocol import (
    SB2ACHandshake,
    SB2ACState,
)
from custom_components.solix_ble.SolixBLE.sb3_protocol import (
    SB3_INITIAL_AES_KEY,
    SB3_INITIAL_NONCE,
    aes_gcm_decrypt,
    aes_gcm_encrypt,
    build_packet,
    encode_public_key,
    parse_packet,
)


ACCOUNT_ID = "0123456789abcdef0123456789abcdef01234567"


def _bootstrap_response(command: bytes, plaintext: bytes = b"\x00") -> bytes:
    return build_packet(
        b"\x03\x01\x01",
        command,
        aes_gcm_encrypt(SB3_INITIAL_AES_KEY, SB3_INITIAL_NONCE, plaintext),
    )


def test_sb2ac_handshake_uses_4005_and_reaches_session_ready() -> None:
    """The owned SB2 AC capture requires 4005/4805 before dynamic 4021."""
    handshake = SB2ACHandshake(ACCOUNT_ID)

    packet = parse_packet(handshake.start())
    assert packet.command == bytes.fromhex("4001")
    assert aes_gcm_decrypt(SB3_INITIAL_AES_KEY, SB3_INITIAL_NONCE, packet.payload).endswith(
        bytes.fromhex("a200")
    )

    packet = parse_packet(handshake.receive(_bootstrap_response(bytes.fromhex("4801"))))
    assert packet.command == bytes.fromhex("4003")
    packet = parse_packet(handshake.receive(_bootstrap_response(bytes.fromhex("4803"))))
    assert packet.command == bytes.fromhex("4029")

    packet = parse_packet(handshake.receive(_bootstrap_response(bytes.fromhex("4829"))))
    assert packet.command == bytes.fromhex("4005")
    assert handshake.state is SB2ACState.WAIT_4805

    packet = parse_packet(handshake.receive(_bootstrap_response(bytes.fromhex("4805"))))
    assert packet.command == bytes.fromhex("4021")
    assert handshake.state is SB2ACState.WAIT_4821

    device_key = ec.generate_private_key(ec.SECP256R1())
    packet = parse_packet(
        handshake.receive(
            _bootstrap_response(
                bytes.fromhex("4821"),
                b"\x00\xa1\x40" + encode_public_key(device_key.public_key()),
            )
        )
    )
    assert packet.command == bytes.fromhex("4022")
    assert handshake.session_key is not None
    assert handshake.session_nonce is not None

    session_response = lambda command: build_packet(
        b"\x03\x01\x01",
        command,
        aes_gcm_encrypt(handshake.session_key, handshake.session_nonce, b"\x04"),
    )
    packet = parse_packet(handshake.receive(session_response(bytes.fromhex("4822"))))
    assert packet.command == bytes.fromhex("4027")
    packet = parse_packet(handshake.receive(session_response(bytes.fromhex("4827"))))
    assert handshake.session_ready
    assert packet.command == bytes.fromhex("4040")
    assert aes_gcm_decrypt(
        handshake.session_key, handshake.session_nonce, packet.payload
    ).startswith(bytes.fromhex("a10121fe0503"))

    device_info_packet = parse_packet(
        handshake.build_command(bytes.fromhex("4069"), bytes.fromhex("a10121"))
    )
    assert device_info_packet.command == bytes.fromhex("4069")
    assert aes_gcm_decrypt(
        handshake.session_key, handshake.session_nonce, device_info_packet.payload
    ).startswith(bytes.fromhex("a10121fe0503"))
