"""Generowanie klucza aplikacji Enable Banking lokalnie (klucz prywatny nie opuszcza HA).

Do Control Panelu EB wkleja się tylko self-signed certyfikat (`.crt`).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def generate_key_and_cert(
    out_prefix: Path, *, common_name: str = "ha-budget-app", days: int = 3650, bits: int = 4096
) -> tuple[Path, Path]:
    """Tworzy `<prefix>.pem` (PKCS#8, 0600) i `<prefix>.crt`. Nie nadpisuje istniejących plików."""
    key_path = out_prefix.with_suffix(".pem")
    crt_path = out_prefix.with_suffix(".crt")
    for path in (key_path, crt_path):
        if path.exists():
            raise FileExistsError(f"{path} już istnieje — nie nadpisuję klucza")

    key = rsa.generate_private_key(public_exponent=65537, key_size=bits)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=days))
        .sign(key, hashes.SHA256())
    )

    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(pem)
    crt_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return key_path, crt_path
