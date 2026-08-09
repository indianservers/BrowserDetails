from app.services.privacy import anonymize_ip, redact_sensitive_payload


def test_anonymize_ip_truncates_ipv4_and_ipv6():
    assert anonymize_ip("203.0.113.42") == "203.0.113.0"
    assert anonymize_ip("2001:db8:abcd:1234::1") == "2001:db8:abcd::"


def test_redacts_sensitive_payload_keys():
    payload = {"lesson_id": "algebra-101", "auth_token": "secret", "nested": {"email": "a@example.com"}}
    assert redact_sensitive_payload(payload) == {
        "lesson_id": "algebra-101",
        "auth_token": "[REDACTED]",
        "nested": {"email": "[REDACTED]"},
    }
