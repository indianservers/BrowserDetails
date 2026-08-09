from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field

SafeActionType = Literal[
    "REFRESH_BROWSER_INFORMATION",
    "MEASURE_API_LATENCY",
    "MEASURE_WEBSOCKET_LATENCY",
    "RUN_APPLICATION_HEALTH_CHECK",
    "CHECK_SUPPORTED_BROWSER_APIS",
    "RECALCULATE_VIEWPORT",
    "COLLECT_PERFORMANCE_METRICS",
    "VERIFY_SDK_VERSION",
    "REQUEST_RECONNECT",
    "CLEAR_MONITORING_IDENTIFIER",
    "DISPLAY_SUPPORT_NOTIFICATION",
    "DISPLAY_SUPPORT_MESSAGE",
    "DISPLAY_SUPPORT_IMAGE",
    "REQUEST_SUPPORT_USERNAME",
    "SHOW_SUPPORT_BANNER",
    "HIGHLIGHT_PAGE_ELEMENT",
    "SCROLL_TO_PAGE_ELEMENT",
    "CLEAR_SUPPORT_OVERLAYS",
    "ASK_REFRESH_PAGE",
    "OPEN_APPROVED_SUPPORT_PAGE",
    "OPEN_APPROVED_SUPPORT_IFRAME",
    "REQUEST_DIAGNOSTIC_LOG_UPLOAD",
]


class DiagnosticActionCreate(BaseModel):
    session_id: str
    type: SafeActionType
    parameters: dict[str, Any] = Field(default_factory=dict)
    expires_at: datetime


class DiagnosticActionOut(BaseModel):
    action_id: str
    type: SafeActionType
    parameters: dict[str, Any]
    user_visible_description: str
    expires_at: datetime
