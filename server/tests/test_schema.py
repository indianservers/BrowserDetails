from pydantic import ValidationError
import pytest

from app.schemas.client import ClientEventRequest, RegisterClientRequest


def test_event_name_schema_rejects_html():
    with pytest.raises(ValidationError):
        ClientEventRequest(event_id="event_1234567890123456", session_id="s", project_id="p", name="<script>")


def test_registration_redacts_query_string_from_route():
    payload = RegisterClientRequest(
        project_id="PUBLIC_PROJECT_1",
        session_id="session_1234567890123456",
        visitor_id="visitor_1234567890123456",
        origin="https://example.com",
        route="/checkout?token=secret",
        consent_state="GRANTED",
        sdk_version="0.1.0",
        diagnostics={"browser": {}, "display": {}, "graphics": {}, "network": {}, "page": {}},
    )
    assert payload.route == "/checkout"
