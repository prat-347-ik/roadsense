from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519


# Default key storage path (ignored in .gitignore)
DEFAULT_KEY_DIR = Path(__file__).resolve().parent / "keys"
DEFAULT_PRIVATE_KEY_PATH = DEFAULT_KEY_DIR / "device_private_key.pem"


class DeviceSigner:
    """Manages asymmetric device keypair and cryptographic signing for edge bursts.

    NOTE ON BACKEND COMPATIBILITY:
    The backend's verify_signature() function in `backend/app/core/security.py` is currently
    a development stub that accepts any non-empty signature string.
    DeviceSigner implements production-grade Ed25519 asymmetric cryptographic signing today
    (per architecture specification §14.2) so that when the backend activates real asymmetric
    public-key verification against registered devices, ZERO changes will be required on the edge.
    """

    def __init__(self, key_path: str | Path | None = None):
        self.key_path = Path(key_path) if key_path else DEFAULT_PRIVATE_KEY_PATH
        self._private_key: ed25519.Ed25519PrivateKey = self._load_or_generate_key()

    def _load_or_generate_key(self) -> ed25519.Ed25519PrivateKey:
        """Load private key from disk or generate and persist a fresh keypair."""
        if self.key_path.exists():
            try:
                pem_data = self.key_path.read_bytes()
                return serialization.load_pem_private_key(pem_data, password=None)  # type: ignore
            except Exception:
                # If existing key file corrupted, generate new
                pass

        # Generate new Ed25519 keypair
        private_key = ed25519.Ed25519PrivateKey.generate()
        self.key_path.parent.mkdir(parents=True, exist_ok=True)

        pem_data = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        self.key_path.write_bytes(pem_data)
        return private_key

    @property
    def public_key_hex(self) -> str:
        """Public key formatted as hex string."""
        pub_bytes = self._private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return pub_bytes.hex()

    def sign_payload(self, payload: dict[str, Any]) -> str:
        """Signs a burst payload dictionary with the device's Ed25519 private key.

        Excludes the 'sig' key itself if present, sorts keys canonically, and returns
        the signature formatted as a hex string.
        """
        # Canonical representation of fields (excluding existing signature)
        clean_payload = {k: v for k, v in payload.items() if k != "sig"}
        canonical_bytes = json.dumps(clean_payload, sort_keys=True, default=str).encode("utf-8")

        sig_bytes = self._private_key.sign(canonical_bytes)
        return sig_bytes.hex()

    @staticmethod
    def verify_signature(payload: dict[str, Any], sig_hex: str, public_key_hex: str) -> bool:
        """Verify an Ed25519 signature given payload, hex signature, and hex public key."""
        try:
            pub_bytes = bytes.fromhex(public_key_hex)
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)

            clean_payload = {k: v for k, v in payload.items() if k != "sig"}
            canonical_bytes = json.dumps(clean_payload, sort_keys=True, default=str).encode("utf-8")

            sig_bytes = bytes.fromhex(sig_hex)
            public_key.verify(sig_bytes, canonical_bytes)
            return True
        except Exception:
            return False
