"""Solarbank 3 A17C5 secure BLE handshake helpers.

Implements the authenticated outer AES-GCM layer observed in the official app,
generates a fresh secp256r1 key pair for every connection, derives the per-session
AES-GCM material, sends a dynamic 4022 identity-authentication request and
strictly validates the authenticated 4822 success response.

The account identifier is loaded from ``/config/solix_sb3_account_id.txt`` and
must be the 40-character hexadecimal Anker cloud user ID.  Once its authenticated
``4822`` acknowledgement has been received, the session continues with the
AES-GCM protected 4027/4827 exchange and starts the status stream with 4040.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import logging
from pathlib import Path
import secrets
import time
from typing import Any
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .const import BASE_TIMESTAMP

_LOGGER = logging.getLogger(__name__)

SB3_ACCOUNT_ID_PATH = Path("/config/solix_sb3_account_id.txt")
SB3_ACCOUNT_ID_HEX_LENGTH = 40
SB3_4822_SUCCESS_PLAINTEXT = b"\x04"
SB3_DEFAULT_CLIENT_ID = "79ebed35-dc9c-4904-b40c-72c4e8363a10"
SB3_SET_SCHEDULE_COMMAND = bytes.fromhex("405e")

# Initial secure-conference material reconstructed from the A17C5 app path.
# AES-GCM returns ciphertext followed by a 16-byte authentication tag.
SB3_INITIAL_AES_KEY = bytes.fromhex("b8ff7422955d4eb6d554a2c470280559")
SB3_INITIAL_NONCE = bytes.fromhex("6ba3e3f2f3a60f2971ce5d1f")
SB3_AES_GCM_AAD = bytes.fromhex("3322110077665544bbaa9988ffeeddcc")

# These four packets are stable in the available successful captures.  They are
# intentionally kept isolated because 4029 contains account/device binding data.
SB3_4001 = bytes.fromhex(
    "ff09220003000140010a824f0bbd508bb2178c3054ae2df691dab7ce7dd037c5e38b"
)
SB3_4003 = bytes.fromhex(
    "ff09290003000140030a824e0bbd508bb25db5286d496f964ade328b233f57fcf51eb1f2639d69c6f9"
)
SB3_4029 = bytes.fromhex(
    "ff094a0003000140290a824e0bbd508b9acc816cf1285604b0b741b6b202d4f3b4c28ad6630662ca07b3fef57148a0835a890e253dcdeaf36c2a4ca1d6229283bc963af531b711fd239a"
)
SB3_4005 = bytes.fromhex(
    "ff092f0003000140050a824e0bbd508bb25db5286d496f9670823925d138f20cc16133c3ead23c3a1da7e14615bdb8"
)


class SB3State(str, Enum):
    IDLE = "idle"
    WAIT_4801 = "wait_4801"
    WAIT_4803 = "wait_4803"
    WAIT_4829 = "wait_4829"
    WAIT_4805 = "wait_4805"
    WAIT_4821 = "wait_4821"
    NEED_ACCOUNT_ID = "need_account_id"
    WAIT_4822 = "wait_4822"
    IDENTITY_AUTHENTICATED = "identity_authenticated"
    WAIT_4827 = "wait_4827"
    SESSION_READY = "session_ready"
    FAILED = "failed"


def xor_checksum(data: bytes) -> bytes:
    """Return the one-byte XOR checksum used by the FF09 framing."""
    value = 0
    for byte in data:
        value ^= byte
    return bytes((value,))


def build_packet(pattern: bytes, command: bytes, payload: bytes) -> bytes:
    """Build one validated Solix FF09 packet."""
    if len(pattern) != 3:
        raise ValueError("pattern must be exactly 3 bytes")
    if len(command) != 2:
        raise ValueError("command must be exactly 2 bytes")
    length = 2 + 2 + 3 + 2 + len(payload) + 1
    packet = b"\xff\x09" + length.to_bytes(2, "little") + pattern + command + payload
    return packet + xor_checksum(packet)


@dataclass(slots=True)
class SB3Packet:
    raw: bytes
    pattern: bytes
    command: bytes
    payload: bytes

    @property
    def command_hex(self) -> str:
        return self.command.hex()


def parse_packet(packet: bytes) -> SB3Packet:
    """Validate and split one FF09 packet."""
    if len(packet) < 10 or packet[:2] != b"\xff\x09":
        raise ValueError("invalid FF09 packet")
    if int.from_bytes(packet[2:4], "little") != len(packet):
        raise ValueError("packet length mismatch")
    if packet[-1:] != xor_checksum(packet[:-1]):
        raise ValueError("packet checksum mismatch")
    return SB3Packet(packet, packet[4:7], packet[7:9], packet[9:-1])


def aes_gcm_encrypt(key: bytes, nonce: bytes, plaintext: bytes) -> bytes:
    """Encrypt and authenticate an A17C5 payload."""
    return AESGCM(key).encrypt(nonce, plaintext, SB3_AES_GCM_AAD)


def aes_gcm_decrypt(key: bytes, nonce: bytes, payload: bytes) -> bytes:
    """Authenticate and decrypt an A17C5 payload."""
    try:
        return AESGCM(key).decrypt(nonce, payload, SB3_AES_GCM_AAD)
    except InvalidTag as err:
        raise ValueError("A17C5 AES-GCM authentication tag is invalid") from err


def encode_public_key(public_key: ec.EllipticCurvePublicKey) -> bytes:
    """Encode secp256r1 as the app's 64-byte X||Y form."""
    numbers = public_key.public_numbers()
    return numbers.x.to_bytes(32, "big") + numbers.y.to_bytes(32, "big")


def decode_public_key(raw_key: bytes) -> ec.EllipticCurvePublicKey:
    """Decode the app's 64-byte X||Y secp256r1 public key."""
    if len(raw_key) != 64:
        raise ValueError(f"expected a 64-byte P-256 public key, got {len(raw_key)}")
    return ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), b"\x04" + raw_key
    )


def extract_public_key_plaintext(plaintext: bytes, *, response: bool) -> bytes:
    """Extract A1/64 public-key data from decrypted 4021 or 4821 plaintext."""
    expected_prefix = b"\x00\xa1\x40" if response else b"\xa1\x40"
    if not plaintext.startswith(expected_prefix):
        raise ValueError(
            f"unexpected public-key plaintext prefix: {plaintext[:3].hex()}"
        )
    raw_key = plaintext[len(expected_prefix):]
    if len(raw_key) != 64:
        raise ValueError(f"unexpected public-key data length: {len(raw_key)}")
    # Parsing the point also proves that it lies on secp256r1.
    decode_public_key(raw_key)
    return raw_key


def build_public_key_request(public_key: ec.EllipticCurvePublicKey) -> bytes:
    """Build a fresh outer-layer encrypted 4021 request."""
    plaintext = b"\xa1\x40" + encode_public_key(public_key)
    encrypted = aes_gcm_encrypt(
        SB3_INITIAL_AES_KEY, SB3_INITIAL_NONCE, plaintext
    )
    return build_packet(b"\x03\x00\x01", b"\x40\x21", encrypted)



def validate_sb3_account_id(account_id: str) -> str:
    """Validate and normalize the Anker cloud user ID used by 4022."""
    value = account_id.strip().lower()
    if len(value) != SB3_ACCOUNT_ID_HEX_LENGTH:
        raise ValueError(
            "Solarbank 3 account ID must be exactly "
            f"{SB3_ACCOUNT_ID_HEX_LENGTH} hexadecimal characters"
        )
    if any(char not in "0123456789abcdef" for char in value):
        raise ValueError("Solarbank 3 account ID contains non-hexadecimal characters")
    return value

def build_account_auth_plaintext(account_id: str, timestamp: int | None = None) -> bytes:
    """Build the A1 timestamp + A2 account ID parameter set used by 4022."""
    normalized_account_id = validate_sb3_account_id(account_id)
    account_bytes = normalized_account_id.encode("ascii")
    if timestamp is None:
        timestamp = int(time.time())
    if not 0 <= timestamp <= 0xFFFFFFFF:
        raise ValueError("timestamp does not fit in four bytes")
    return (
        b"\xa1\x04"
        + timestamp.to_bytes(4, "little")
        + b"\xa2"
        + bytes((len(account_bytes),))
        + account_bytes
    )


def build_account_auth_packet(
    account_id: str,
    session_key: bytes,
    session_nonce: bytes,
    timestamp: int | None = None,
) -> bytes:
    """Build one dynamic, session-bound 4022 request."""
    plaintext = build_account_auth_plaintext(account_id, timestamp)
    encrypted = aes_gcm_encrypt(session_key, session_nonce, plaintext)
    return build_packet(b"\x03\x00\x01", b"\x40\x22", encrypted)


def validate_sb3_client_id(client_id: str) -> str:
    """Validate the 4027 security identifier.

    The official Android capture uses a 40-character hexadecimal identifier
    (``a228``) for 4027. Keep accepting the earlier UUID form for callers and
    protocol tests that still use it.
    """
    value = str(client_id).strip().lower()
    if len(value) == 40 and all(char in "0123456789abcdef" for char in value):
        return value
    try:
        return str(UUID(value))
    except (ValueError, AttributeError) as err:
        raise ValueError(
            "Solarbank 3 client ID must be a UUID or 40-character hexadecimal ID"
        ) from err


def build_security_auth_plaintext(
    client_id: str = SB3_DEFAULT_CLIENT_ID, timestamp: int | None = None
) -> bytes:
    """Build the A1 timestamp + A2 security identifier used by 4027."""
    client_bytes = validate_sb3_client_id(client_id).encode("ascii")
    if timestamp is None:
        timestamp = int(time.time())
    if not 0 <= timestamp <= 0xFFFFFFFF:
        raise ValueError("timestamp does not fit in four bytes")
    return (
        b"\xa1\x04"
        + timestamp.to_bytes(4, "little")
        + b"\xa2"
        + bytes((len(client_bytes),))
        + client_bytes
    )


def build_security_auth_packet(
    session_key: bytes,
    session_nonce: bytes,
    client_id: str = SB3_DEFAULT_CLIENT_ID,
    timestamp: int | None = None,
) -> bytes:
    """Build the authenticated, session-bound 4027 request."""
    return build_packet(
        b"\x03\x00\x01",
        b"\x40\x27",
        aes_gcm_encrypt(
            session_key,
            session_nonce,
            build_security_auth_plaintext(client_id, timestamp),
        ),
    )


def build_telemetry_request_plaintext(timestamp: int | None = None) -> bytes:
    """Build the replay-protected status query used by command 4040.

    The official Android capture contains a ten-byte plaintext.  It uses the
    common Solix command timestamp TLV (``fe0503``), not the Prime-only
    ``fe04`` variant and not the short three-byte subscription payload.
    """
    if timestamp is None:
        timestamp = int.from_bytes(bytes.fromhex(BASE_TIMESTAMP), "little")
    if not 0 <= timestamp <= 0xFFFFFFFF:
        raise ValueError("timestamp does not fit in four bytes")
    return b"\xa1\x01\x21\xfe\x05\x03" + timestamp.to_bytes(4, "little")


def build_telemetry_request_packet(
    session_key: bytes, session_nonce: bytes, timestamp: int | None = None
) -> bytes:
    """Build the encrypted 4040 status request."""
    return build_packet(
        b"\x03\x00\x0f",
        b"\x40\x40",
        aes_gcm_encrypt(
            session_key,
            session_nonce,
            build_telemetry_request_plaintext(timestamp),
        ),
    )


def build_sb3_schedule_plaintext(
    power_w: int,
    *,
    start_minutes: int = 0,
    end_minutes: int = 1440,
    fd_token: bytes | None = None,
) -> bytes:
    """Build the Solarbank 3 ``405e`` schedule payload.

    The official app writes one schedule block for every weekday.  The
    captured A17C5 packet has seven 22-byte blocks, followed by a fresh
    ``fd0503`` token.  The common ``fe0503`` replay timestamp is appended by
    :meth:`SolixBLEDevice._send_command` immediately before encryption.

    Each block contains a 00:00--24:00 interval, the requested output power
    and the captured ``0x0050`` trailer.
    Keeping the token injectable makes the binary layout testable while the
    default generates the same fresh four-byte value as the Android app.
    """
    if not isinstance(power_w, int) or isinstance(power_w, bool):
        raise TypeError("power_w must be an integer")
    if not 0 <= power_w <= 800:
        raise ValueError("power_w must be between 0 and 800 W")
    if not 0 <= start_minutes <= 1440:
        raise ValueError("start_minutes must be between 0 and 1440")
    if not 0 <= end_minutes <= 1440 or end_minutes < start_minutes:
        raise ValueError("end_minutes must be between start_minutes and 1440")
    if fd_token is None:
        fd_token = secrets.token_bytes(4)
    if len(fd_token) != 4:
        raise ValueError("fd_token must contain exactly four bytes")

    schedule = bytearray(b"\xa1\x01\x21\xa2\x02\x01\x01")
    slot = (
        start_minutes.to_bytes(2, "little")
        + end_minutes.to_bytes(2, "little")
        + power_w.to_bytes(2, "little")
        + b"\x50\x00"
    )
    for day in range(7):
        base = 0xA3 + 4 * day
        schedule.extend(bytes((base,)) + b"\x02\x01\x01")
        schedule.extend(bytes((base + 1,)) + b"\x09\x04" + slot)
        schedule.extend(bytes((base + 2,)) + b"\x02\x01\x00")
        schedule.extend(bytes((base + 3,)) + b"\x01\x04")

    schedule.extend(b"\xfd\x05\x03" + fd_token)
    if len(schedule) != 168:
        raise AssertionError(f"unexpected SB3 schedule body length: {len(schedule)}")
    return bytes(schedule)


async def load_sb3_account_id(path: Path = SB3_ACCOUNT_ID_PATH) -> str | None:
    """Load an explicitly configured account ID without blocking HA's loop."""
    def _read() -> str | None:
        if not path.exists():
            return None
        value = path.read_text(encoding="utf-8").strip()
        return value or None

    value = await asyncio.to_thread(_read)
    if value is None:
        return None
    return validate_sb3_account_id(value)


@dataclass(slots=True)
class SB3Transcript:
    device_name: str
    address: str
    started: float = field(default_factory=time.monotonic)
    events: list[dict[str, Any]] = field(default_factory=list)

    def add(self, direction: str, packet: bytes, note: str = "") -> None:
        parsed = parse_packet(packet)
        self.events.append(
            {
                "t": round(time.monotonic() - self.started, 6),
                "direction": direction,
                "pattern": parsed.pattern.hex(),
                "command": parsed.command.hex(),
                "payload": parsed.payload.hex(),
                "packet": packet.hex(),
                "note": note,
            }
        )

    async def export(self, directory: str | Path = "/config") -> Path:
        """Write the transcript outside Home Assistant's event loop."""
        return await asyncio.to_thread(self._export_sync, directory)

    def _export_sync(self, directory: str | Path) -> Path:
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        safe_address = self.address.replace(":", "").replace("-", "")
        path = target / f"solix_sb3_transcript_{safe_address}_{int(time.time())}.json"
        path.write_text(
            json.dumps(
                {
                    "device_name": self.device_name,
                    "address": self.address,
                    "events": self.events,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return path


class SB3Handshake:
    """Strict A17C5 state machine through dynamic ECDH and optional 4022."""

    def __init__(
        self,
        device_name: str,
        address: str,
        account_id: str | None = None,
        client_id: str = SB3_DEFAULT_CLIENT_ID,
    ) -> None:
        self.state = SB3State.IDLE
        self.transcript = SB3Transcript(device_name, address)
        self.account_id = account_id
        # The official app binds 4027 to the same 40-character account
        # identifier used by 4022. Fall back to the historical UUID only when
        # no account ID is available (for compatibility/testing).
        self.client_id = validate_sb3_client_id(account_id or client_id)
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        self.client_public_key = encode_public_key(self.private_key.public_key())
        self.device_public_key: bytes | None = None
        self.session_key: bytes | None = None
        self.session_nonce: bytes | None = None
        self.last_decrypted_plaintext: bytes | None = None
        self._telemetry_timestamp_started = time.monotonic()
        self._last_telemetry_timestamp: int | None = None

    def next_telemetry_timestamp(self) -> int:
        """Return the next replay-protection timestamp for an SB3 command."""
        base_timestamp = int.from_bytes(bytes.fromhex(BASE_TIMESTAMP), "little")
        elapsed = int(time.monotonic() - self._telemetry_timestamp_started)
        timestamp = base_timestamp + elapsed
        if self._last_telemetry_timestamp is not None:
            timestamp = max(timestamp, self._last_telemetry_timestamp + 1)
        self._last_telemetry_timestamp = timestamp
        return timestamp

    def start(self) -> bytes:
        if self.state is not SB3State.IDLE:
            raise RuntimeError(f"handshake already started: {self.state}")
        self.state = SB3State.WAIT_4801
        self.transcript.add("tx", SB3_4001, "stable negotiation start")
        return SB3_4001

    def _derive_session(self, encrypted_4821: bytes) -> None:
        plaintext = aes_gcm_decrypt(
            SB3_INITIAL_AES_KEY, SB3_INITIAL_NONCE, encrypted_4821
        )
        self.last_decrypted_plaintext = plaintext
        raw_device_key = extract_public_key_plaintext(plaintext, response=True)
        device_key = decode_public_key(raw_device_key)
        shared_secret = self.private_key.exchange(ec.ECDH(), device_key)
        if len(shared_secret) != 32:
            raise ValueError(
                f"unexpected P-256 ECDH secret length: {len(shared_secret)}"
            )
        self.device_public_key = raw_device_key
        self.session_key = shared_secret[:16]
        self.session_nonce = shared_secret[16:28]
        fingerprint = hashlib.sha256(shared_secret).hexdigest()[:16]
        _LOGGER.warning(
            "SB3 dynamic ECDH succeeded: curve=secp256r1, "
            "device_public_key=%s, session_fingerprint=%s",
            raw_device_key.hex(),
            fingerprint,
        )

    def receive(self, packet: bytes) -> bytes | None:
        parsed = parse_packet(packet)
        self.transcript.add("rx", packet)
        expected = {
            SB3State.WAIT_4801: "4801",
            SB3State.WAIT_4803: "4803",
            SB3State.WAIT_4829: "4829",
            SB3State.WAIT_4805: "4805",
            SB3State.WAIT_4821: "4821",
            SB3State.WAIT_4822: "4822",
            SB3State.WAIT_4827: "4827",
        }.get(self.state)
        if expected is None or parsed.command_hex != expected:
            self.state = SB3State.FAILED
            raise ValueError(f"expected {expected}, got {parsed.command_hex}")

        if self.state is SB3State.WAIT_4801:
            self.state = SB3State.WAIT_4803
            reply = SB3_4003
            note = "stable negotiation packet"
        elif self.state is SB3State.WAIT_4803:
            self.state = SB3State.WAIT_4829
            reply = SB3_4029
            note = "captured account/device binding packet"
        elif self.state is SB3State.WAIT_4829:
            self.state = SB3State.WAIT_4805
            reply = SB3_4005
            note = "stable negotiation packet"
        elif self.state is SB3State.WAIT_4805:
            self.state = SB3State.WAIT_4821
            reply = build_public_key_request(self.private_key.public_key())
            note = "dynamic secp256r1 public-key request"
        elif self.state is SB3State.WAIT_4821:
            self._derive_session(parsed.payload)
            if self.account_id is None:
                self.state = SB3State.NEED_ACCOUNT_ID
                return None
            assert self.session_key is not None
            assert self.session_nonce is not None
            reply = build_account_auth_packet(
                self.account_id, self.session_key, self.session_nonce
            )
            self.state = SB3State.WAIT_4822
            note = (
                "dynamic account-auth request; account ID intentionally omitted "
                "from transcript"
            )
        elif self.state is SB3State.WAIT_4822:
            assert self.session_key is not None
            assert self.session_nonce is not None
            plaintext = aes_gcm_decrypt(
                self.session_key, self.session_nonce, parsed.payload
            )
            self.last_decrypted_plaintext = plaintext
            if plaintext != SB3_4822_SUCCESS_PLAINTEXT:
                self.state = SB3State.FAILED
                raise ValueError(
                    "SB3 4822 identity-authentication response was authenticated "
                    f"but not successful: plaintext={plaintext.hex()}"
                )
            self.state = SB3State.IDENTITY_AUTHENTICATED
            _LOGGER.warning(
                "SB3 identity authentication accepted: authenticated 4822 plaintext=04"
            )
            reply = build_security_auth_packet(
                self.session_key, self.session_nonce, self.client_id
            )
            self.state = SB3State.WAIT_4827
            note = "dynamic client-security authentication request"
        else:
            assert self.session_key is not None
            assert self.session_nonce is not None
            plaintext = aes_gcm_decrypt(
                self.session_key, self.session_nonce, parsed.payload
            )
            self.last_decrypted_plaintext = plaintext
            self.state = SB3State.SESSION_READY
            _LOGGER.warning(
                "SB3 client-security authentication accepted: 4827 plaintext=%s",
                plaintext.hex(),
            )
            reply = build_telemetry_request_packet(
                self.session_key,
                self.session_nonce,
                self.next_telemetry_timestamp(),
            )
            note = "session ready; request first telemetry update"

        self.transcript.add("tx", reply, note)
        return reply

    @property
    def identity_authenticated(self) -> bool:
        """Return True only after an authenticated 4822 success response."""
        return self.state in {SB3State.IDENTITY_AUTHENTICATED, SB3State.WAIT_4827, SB3State.SESSION_READY}

    @property
    def session_ready(self) -> bool:
        """Return True only after an authenticated 4827 response."""
        return self.state is SB3State.SESSION_READY

    @property
    def checkpoint_complete(self) -> bool:
        return self.state in {
            SB3State.NEED_ACCOUNT_ID,
            SB3State.SESSION_READY,
        }
