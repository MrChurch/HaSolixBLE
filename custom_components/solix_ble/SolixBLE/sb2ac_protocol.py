"""Solarbank 2 AC dynamic BLE session helpers.

This transport was reconstructed from an owned Solarbank 2 AC capture.  It
uses the same outer AES-GCM bootstrap as the A17C5 family, but deliberately
has its own state machine. The owned capture confirms the required
``4005``/``4805`` bootstrap step before the P-256 key exchange and uses
``4022`` for timezone setup. Keeping it separate prevents changes to the
established Solarbank 3 authentication path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import time

from cryptography.hazmat.primitives.asymmetric import ec

from .sb3_protocol import (
    SB3_INITIAL_AES_KEY,
    SB3_INITIAL_NONCE,
    aes_gcm_decrypt,
    aes_gcm_encrypt,
    build_packet,
    decode_public_key,
    encode_public_key,
    extract_public_key_plaintext,
    parse_packet,
    validate_sb3_account_id,
)


class SB2ACState(str, Enum):
    """States observed in the Solarbank 2 AC dynamic session."""

    IDLE = "idle"
    WAIT_4801 = "wait_4801"
    WAIT_4803 = "wait_4803"
    WAIT_4829 = "wait_4829"
    WAIT_4805 = "wait_4805"
    WAIT_4821 = "wait_4821"
    WAIT_4822 = "wait_4822"
    WAIT_4827 = "wait_4827"
    SESSION_READY = "session_ready"
    FAILED = "failed"


@dataclass(slots=True)
class SB2ACHandshake:
    """Build and validate the capture-derived Solarbank 2 AC handshake."""

    account_id: str
    state: SB2ACState = SB2ACState.IDLE
    private_key: ec.EllipticCurvePrivateKey | None = None
    session_key: bytes | None = None
    session_nonce: bytes | None = None
    _last_timestamp: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.account_id = validate_sb3_account_id(self.account_id)

    @property
    def session_ready(self) -> bool:
        """Return whether authenticated session encryption is available."""
        return self.state is SB2ACState.SESSION_READY

    def _timestamp(self) -> int:
        timestamp = max(int(time.time()), self._last_timestamp + 1)
        self._last_timestamp = timestamp
        return timestamp

    def next_timestamp(self) -> int:
        """Return a new session timestamp for one or more related requests."""
        return self._timestamp()

    @staticmethod
    def _bootstrap_packet(command: bytes, plaintext: bytes) -> bytes:
        return build_packet(
            b"\x03\x00\x01",
            command,
            aes_gcm_encrypt(SB3_INITIAL_AES_KEY, SB3_INITIAL_NONCE, plaintext),
        )

    @staticmethod
    def _decrypt_bootstrap(payload: bytes) -> bytes:
        return aes_gcm_decrypt(SB3_INITIAL_AES_KEY, SB3_INITIAL_NONCE, payload)

    def _session_packet(self, command: bytes, plaintext: bytes) -> bytes:
        if self.session_key is None or self.session_nonce is None:
            raise ValueError("Solarbank 2 AC session key is unavailable")
        return build_packet(
            b"\x03\x00\x0f",
            command,
            aes_gcm_encrypt(self.session_key, self.session_nonce, plaintext),
        )

    def start(self) -> bytes:
        """Start with the observed dynamic ``4001`` request."""
        if self.state is not SB2ACState.IDLE:
            raise ValueError(f"cannot start handshake in state {self.state}")
        plaintext = b"\xa1\x04" + self._timestamp().to_bytes(4, "little") + b"\xa2\x00"
        self.state = SB2ACState.WAIT_4801
        return self._bootstrap_packet(b"\x40\x01", plaintext)

    def _timezone_payload(self) -> bytes:
        """Build the Berlin POSIX timezone setup observed before ``4822``."""
        offset = datetime.now().astimezone().utcoffset()
        seconds = int(offset.total_seconds()) if offset is not None else 0
        # The app uses the inverted UTC offset: CEST (+7200) is encoded -7200.
        timezone = b"CET-1CEST,M3.5.0,M10.5.0/3"
        return (
            b"\xa1\x04"
            + self._timestamp().to_bytes(4, "little")
            + b"\xa2\x00\xa3\x04"
            + (-seconds).to_bytes(4, "little", signed=True)
            + b"\xa5"
            + bytes((len(timezone),))
            + timezone
        )

    def receive(self, raw_packet: bytes) -> bytes | None:
        """Accept one response and return the next protocol packet."""
        packet = parse_packet(raw_packet)
        command = packet.command

        try:
            if self.state is SB2ACState.WAIT_4801 and command == b"\x48\x01":
                self._decrypt_bootstrap(packet.payload)
                plaintext = (
                    b"\xa1\x04" + self._timestamp().to_bytes(4, "little")
                    + b"\xa2\x00\xa3\x01\x20\xa4\x02\x00\xf0"
                )
                self.state = SB2ACState.WAIT_4803
                return self._bootstrap_packet(b"\x40\x03", plaintext)

            if self.state is SB2ACState.WAIT_4803 and command == b"\x48\x03":
                self._decrypt_bootstrap(packet.payload)
                plaintext = (
                    b"\xa1\x04" + self._timestamp().to_bytes(4, "little")
                    + b"\xa2\x28" + self.account_id.encode("ascii")
                )
                self.state = SB2ACState.WAIT_4829
                return self._bootstrap_packet(b"\x40\x29", plaintext)

            if self.state is SB2ACState.WAIT_4829 and command == b"\x48\x29":
                self._decrypt_bootstrap(packet.payload)
                plaintext = (
                    b"\xa1\x04" + self._timestamp().to_bytes(4, "little")
                    + b"\xa2\x00\xa3\x01\x20\xa4\x02\x00\xf0"
                    + b"\xa5\x01\x40\xa6\x01\x02"
                )
                self.state = SB2ACState.WAIT_4805
                return self._bootstrap_packet(b"\x40\x05", plaintext)

            if self.state is SB2ACState.WAIT_4805 and command == b"\x48\x05":
                self._decrypt_bootstrap(packet.payload)
                self.private_key = ec.generate_private_key(ec.SECP256R1())
                plaintext = b"\xa1\x40" + encode_public_key(self.private_key.public_key())
                self.state = SB2ACState.WAIT_4821
                return self._bootstrap_packet(b"\x40\x21", plaintext)

            if self.state is SB2ACState.WAIT_4821 and command == b"\x48\x21":
                if self.private_key is None:
                    raise ValueError("missing local P-256 private key")
                device_public_key = decode_public_key(
                    extract_public_key_plaintext(
                        self._decrypt_bootstrap(packet.payload), response=True
                    )
                )
                shared_secret = self.private_key.exchange(ec.ECDH(), device_public_key)
                self.session_key, self.session_nonce = shared_secret[:16], shared_secret[16:28]
                self.state = SB2ACState.WAIT_4822
                return self._session_packet(b"\x40\x22", self._timezone_payload())

            if self.state is SB2ACState.WAIT_4822 and command == b"\x48\x22":
                # AES-GCM authentication is the acceptance criterion. The ACK body
                # differs from the SB3 identity response and is not interpreted.
                self._decrypt_session(packet.payload)
                plaintext = (
                    b"\xa1\x04" + self._timestamp().to_bytes(4, "little")
                    + b"\xa2\x28" + self.account_id.encode("ascii")
                )
                self.state = SB2ACState.WAIT_4827
                return self._session_packet(b"\x40\x27", plaintext)

            if self.state is SB2ACState.WAIT_4827 and command == b"\x48\x27":
                self._decrypt_session(packet.payload)
                self.state = SB2ACState.SESSION_READY
                return self.build_command(b"\x40\x40", b"\xa1\x01\x21")

            raise ValueError(
                f"unexpected SB2 AC response {command.hex()} in state {self.state}"
            )
        except Exception:
            self.state = SB2ACState.FAILED
            raise

    def _decrypt_session(self, payload: bytes) -> bytes:
        if self.session_key is None or self.session_nonce is None:
            raise ValueError("Solarbank 2 AC session key is unavailable")
        return aes_gcm_decrypt(self.session_key, self.session_nonce, payload)

    def decrypt_session_payload(self, payload: bytes) -> bytes:
        """Authenticate and decrypt a post-handshake device payload."""
        return self._decrypt_session(payload)

    def build_command(
        self, command: bytes, payload: bytes, *, timestamp: int | None = None
    ) -> bytes:
        """Encrypt an ordinary command and add its anti-replay timestamp."""
        if not self.session_ready:
            raise ValueError("Solarbank 2 AC session is not ready")
        if timestamp is None:
            timestamp = self._timestamp()
        if not 0 <= timestamp <= 0xFFFFFFFF:
            raise ValueError("timestamp does not fit in four bytes")
        plaintext = payload + b"\xfe\x05\x03" + timestamp.to_bytes(4, "little")
        return self._session_packet(command, plaintext)
