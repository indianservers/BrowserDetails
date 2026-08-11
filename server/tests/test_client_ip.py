from types import SimpleNamespace

from app.api.client import observed_ip


class Headers(dict):
    def get(self, key, default=None):
        return super().get(key.lower(), default)


def test_observed_ip_prefers_forwarded_for_header():
    request = SimpleNamespace(
        headers=Headers({"x-forwarded-for": "203.0.113.42, 10.0.0.1"}),
        client=SimpleNamespace(host="127.0.0.1"),
    )

    assert observed_ip(request) == "203.0.113.42"


def test_observed_ip_falls_back_to_socket_host():
    request = SimpleNamespace(headers=Headers(), client=SimpleNamespace(host="127.0.0.1"))

    assert observed_ip(request) == "127.0.0.1"
