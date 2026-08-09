from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator


ConsentLiteral = Literal["GRANTED", "DENIED", "WITHDRAWN", "IMPLIED"]


class BrowserDiagnostics(BaseModel):
    browser: dict[str, Any] = Field(default_factory=dict)
    display: dict[str, Any] = Field(default_factory=dict)
    graphics: dict[str, Any] = Field(default_factory=dict)
    network: dict[str, Any] = Field(default_factory=dict)
    page: dict[str, Any] = Field(default_factory=dict)


class RegisterClientRequest(BaseModel):
    project_id: str = Field(min_length=8, max_length=64)
    session_id: str = Field(min_length=16, max_length=64)
    visitor_id: str = Field(min_length=16, max_length=64)
    origin: str = Field(max_length=255)
    route: str = Field(default="/", max_length=1024)
    referrer_origin: str | None = Field(default=None, max_length=255)
    consent_state: ConsentLiteral
    sdk_version: str = Field(max_length=32)
    app_version: str | None = Field(default=None, max_length=64)
    diagnostics: BrowserDiagnostics

    @field_validator("route")
    @classmethod
    def reject_query_secret_like_routes(cls, value: str) -> str:
        return value.split("?", 1)[0][:1024]


class RegisterClientResponse(BaseModel):
    accepted: bool
    websocket_url: str
    heartbeat_interval_seconds: int = 20


class HeartbeatRequest(BaseModel):
    session_id: str
    project_id: str
    state: Literal["ACTIVE", "IDLE", "BACKGROUND", "OFFLINE", "CONSENT_WITHDRAWN"]
    route: str | None = Field(default=None, max_length=1024)
    visible: bool | None = None
    latency_ms: int | None = Field(default=None, ge=0, le=60_000)


class ClientEventRequest(BaseModel):
    event_id: str = Field(min_length=16, max_length=64)
    session_id: str
    project_id: str
    name: str = Field(pattern=r"^[a-zA-Z0-9_.:-]{1,128}$")
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime | None = None
