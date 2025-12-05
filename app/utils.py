import hashlib
import hmac
from datetime import datetime
from typing import Optional


def verify_signature(secret: str, payload: bytes, incoming_signature: str | None) -> bool:
    """Validates the webhook HMAC signature when a secret has been configured."""
    if not secret:
        return True
    if not incoming_signature:
        return False

    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    # Support both "sha256=<hash>" and plain hex formats.
    incoming = incoming_signature.split("=", maxsplit=1)
    expected = digest
    provided = incoming[-1].strip()
    return hmac.compare_digest(expected, provided)


def coerce_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def to_storage_timestamp(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def normalize_timestamp(value: Optional[datetime | str]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(microsecond=0).isoformat()
    if " " in value and "T" not in value:
        return value.replace(" ", "T")
    return value
