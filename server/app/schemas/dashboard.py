from datetime import datetime
from pydantic import BaseModel


class SessionSummary(BaseModel):
    session_id: str
    visitor_id: str
    client_name: str | None
    state: str
    consent_state: str
    browser: str | None
    os: str | None
    device: str | None
    route: str | None
    country: str | None
    client_ip: str | None
    live_ws: bool
    last_seen_at: datetime


class DashboardSummary(BaseModel):
    total_visitors: int
    currently_connected: int
    active: int
    idle: int
    background: int
    offline: int
    errors_today: int
    most_common_browser: str | None
    primary_client_ip: str | None
