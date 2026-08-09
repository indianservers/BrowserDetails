import hashlib
import hmac
import ipaddress

from app.config import get_settings


SENSITIVE_KEYS = {
    "password",
    "passcode",
    "otp",
    "token",
    "authorization",
    "cookie",
    "secret",
    "email",
    "phone",
    "card",
    "cvv",
}


def anonymize_ip(ip_value: str | None) -> str | None:
    if not ip_value:
        return None
    try:
        ip = ipaddress.ip_address(ip_value)
    except ValueError:
        return None
    if ip.version == 4:
        parts = ip_value.split(".")
        return ".".join(parts[:3] + ["0"])
    network = ipaddress.ip_network(f"{ip}/48", strict=False)
    return str(network.network_address)


def hash_ip(ip_value: str | None) -> str | None:
    if not ip_value:
        return None
    key = get_settings().jwt_secret.encode("utf-8")
    return hmac.new(key, ip_value.encode("utf-8"), hashlib.sha256).hexdigest()


def redact_sensitive_payload(payload: dict) -> dict:
    redacted: dict = {}
    for key, value in payload.items():
        lowered = key.lower()
        if any(sensitive in lowered for sensitive in SENSITIVE_KEYS):
            redacted[key] = "[REDACTED]"
        elif isinstance(value, dict):
            redacted[key] = redact_sensitive_payload(value)
        elif isinstance(value, str) and len(value) > 512:
            redacted[key] = value[:512]
        else:
            redacted[key] = value
    return redacted
