from urllib.parse import urlparse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class EmptyParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SamplesParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    samples: int = Field(default=5, ge=1, le=20)


class SupportNotificationParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=180)


class SupportMessageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="Support message", min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=1000)
    require_acknowledgement: bool = True


class SupportImageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="Support image", min_length=1, max_length=80)
    image_url: str = Field(min_length=8, max_length=1024)
    caption: str | None = Field(default=None, max_length=300)

    @field_validator("image_url")
    @classmethod
    def only_http_images(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("Image URL must be an http(s) URL without embedded credentials")
        if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1"}:
            raise ValueError("Image URL must use https outside local development")
        return value


class SupportUsernameParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(
        default="Support is asking for your non-sensitive username or display name. Do not enter a password, email address, phone number, OTP, or token.",
        min_length=1,
        max_length=220,
    )


class ApprovedSupportUrlParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(max_length=512)


class ApprovedSupportIframeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(max_length=512)
    title: str = Field(default="Support page", min_length=1, max_length=80)


class SupportBannerParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=240)
    tone: str = Field(default="info", pattern="^(info|success|warning|error)$")
    duration_seconds: int = Field(default=10, ge=3, le=120)


class PageElementParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selector: str = Field(min_length=1, max_length=160)
    label: str | None = Field(default=None, max_length=120)

    @field_validator("selector")
    @classmethod
    def safe_selector(cls, value: str) -> str:
        blocked = ["script", "iframe", "object", "embed", "input[type=password]", "[type=password]"]
        lowered = value.lower()
        if any(item in lowered for item in blocked):
            raise ValueError("Selector targets an unsafe element type")
        if any(token in value for token in ["<", ">", "{", "}"]):
            raise ValueError("Selector contains unsupported characters")
        return value


ACTION_DESCRIPTIONS = {
    "REFRESH_BROWSER_INFORMATION": "Refresh browser diagnostics visible to this page.",
    "MEASURE_API_LATENCY": "Measure API latency from this page.",
    "MEASURE_WEBSOCKET_LATENCY": "Measure WebSocket latency from this page.",
    "RUN_APPLICATION_HEALTH_CHECK": "Run the site owner's approved health check.",
    "CHECK_SUPPORTED_BROWSER_APIS": "Check supported browser APIs without requesting permissions.",
    "RECALCULATE_VIEWPORT": "Recalculate viewport and screen details.",
    "COLLECT_PERFORMANCE_METRICS": "Collect approved page performance metrics.",
    "VERIFY_SDK_VERSION": "Verify whether the monitoring SDK is current.",
    "REQUEST_RECONNECT": "Reconnect this page to the monitoring service.",
    "CLEAR_MONITORING_IDENTIFIER": "Ask the user to clear local monitoring identifiers.",
    "DISPLAY_SUPPORT_NOTIFICATION": "Display a visible support notification.",
    "DISPLAY_SUPPORT_MESSAGE": "Display a visible in-page support message.",
    "DISPLAY_SUPPORT_IMAGE": "Display a visible in-page support image.",
    "REQUEST_SUPPORT_USERNAME": "Ask the user for a non-sensitive support username or display name.",
    "SHOW_SUPPORT_BANNER": "Show a visible support banner on the page.",
    "HIGHLIGHT_PAGE_ELEMENT": "Highlight a page element selected by an approved selector.",
    "SCROLL_TO_PAGE_ELEMENT": "Scroll to a page element selected by an approved selector.",
    "CLEAR_SUPPORT_OVERLAYS": "Clear support overlays created by the monitoring SDK.",
    "ASK_REFRESH_PAGE": "Ask the user to refresh this page.",
    "OPEN_APPROVED_SUPPORT_PAGE": "Ask the user to open an approved support page.",
    "OPEN_APPROVED_SUPPORT_IFRAME": "Open an approved support page in a visible in-page frame.",
    "REQUEST_DIAGNOSTIC_LOG_UPLOAD": "Ask the user to upload approved diagnostic logs.",
}

ACTION_SCHEMAS = {
    "MEASURE_WEBSOCKET_LATENCY": SamplesParams,
    "MEASURE_API_LATENCY": SamplesParams,
    "DISPLAY_SUPPORT_NOTIFICATION": SupportNotificationParams,
    "DISPLAY_SUPPORT_MESSAGE": SupportMessageParams,
    "DISPLAY_SUPPORT_IMAGE": SupportImageParams,
    "REQUEST_SUPPORT_USERNAME": SupportUsernameParams,
    "SHOW_SUPPORT_BANNER": SupportBannerParams,
    "HIGHLIGHT_PAGE_ELEMENT": PageElementParams,
    "SCROLL_TO_PAGE_ELEMENT": PageElementParams,
    "OPEN_APPROVED_SUPPORT_PAGE": ApprovedSupportUrlParams,
    "OPEN_APPROVED_SUPPORT_IFRAME": ApprovedSupportIframeParams,
}


def validate_action_parameters(action_type: str, parameters: dict) -> dict:
    schema = ACTION_SCHEMAS.get(action_type, EmptyParams)
    try:
        return schema(**parameters).model_dump()
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
