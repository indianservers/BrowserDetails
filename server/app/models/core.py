from datetime import datetime
from enum import StrEnum
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ConsentState(StrEnum):
    GRANTED = "GRANTED"
    DENIED = "DENIED"
    WITHDRAWN = "WITHDRAWN"
    IMPLIED = "IMPLIED"


class SessionState(StrEnum):
    CONNECTED = "CONNECTED"
    ACTIVE = "ACTIVE"
    IDLE = "IDLE"
    BACKGROUND = "BACKGROUND"
    OFFLINE = "OFFLINE"
    DISCONNECTED = "DISCONNECTED"
    EXPIRED = "EXPIRED"
    CONSENT_WITHDRAWN = "CONSENT_WITHDRAWN"
    BLOCKED = "BLOCKED"


class ActionStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    environment: Mapped[str] = mapped_column(String(32), default="production")
    consent_mode: Mapped[str] = mapped_column(String(32), default="explicit")
    retention_days: Mapped[int] = mapped_column(Integer, default=90)
    sdk_config: Mapped[dict] = mapped_column(JSON, default=dict)
    url_redaction_rules: Mapped[dict] = mapped_column(JSON, default=dict)
    permitted_events: Mapped[list] = mapped_column(JSON, default=list)
    permitted_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    approved_support_urls: Mapped[list] = mapped_column(JSON, default=list)
    rate_limits: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    origins: Mapped[list["ProjectOrigin"]] = relationship(back_populates="project")


class ProjectOrigin(Base):
    __tablename__ = "project_origins"
    __table_args__ = (UniqueConstraint("project_id", "origin"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    origin: Mapped[str] = mapped_column(String(255), index=True)
    project: Mapped[Project] = relationship(back_populates="origins")


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    mfa_secret: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)


class AdminUserRole(Base):
    __tablename__ = "admin_user_roles"
    __table_args__ = (UniqueConstraint("admin_user_id", "role_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_user_id: Mapped[int] = mapped_column(ForeignKey("admin_users.id"), index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), index=True)


class ProjectSetting(Base):
    __tablename__ = "project_settings"
    __table_args__ = (UniqueConstraint("project_id", "key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    key: Mapped[str] = mapped_column(String(96))
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BrowserVisitor(Base):
    __tablename__ = "browser_visitors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    pseudonymous_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)


class BrowserSession(Base):
    __tablename__ = "browser_sessions"
    __table_args__ = (
        Index("ix_sessions_project_state_last", "project_id", "state", "last_seen_at"),
        Index("ix_sessions_visitor_project", "visitor_id", "project_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    visitor_id: Mapped[int] = mapped_column(ForeignKey("browser_visitors.id"), index=True)
    state: Mapped[SessionState] = mapped_column(Enum(SessionState), default=SessionState.CONNECTED)
    consent_state: Mapped[ConsentState] = mapped_column(Enum(ConsentState), default=ConsentState.DENIED)
    public_ip_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    public_ip_anonymized: Mapped[str | None] = mapped_column(String(64), nullable=True)
    country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    browser_family: Mapped[str | None] = mapped_column(String(64), nullable=True)
    browser_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    operating_system: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    current_origin: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_route: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    referrer_origin: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sdk_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SessionCapabilities(Base):
    __tablename__ = "session_capabilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("browser_sessions.id"), unique=True)
    browser: Mapped[dict] = mapped_column(JSON, default=dict)
    display: Mapped[dict] = mapped_column(JSON, default=dict)
    graphics: Mapped[dict] = mapped_column(JSON, default=dict)
    network: Mapped[dict] = mapped_column(JSON, default=dict)
    page: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SessionConnection(Base):
    __tablename__ = "session_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("browser_sessions.id"), index=True)
    connected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    transport: Mapped[str] = mapped_column(String(32), default="websocket")
    latency_summary: Mapped[dict] = mapped_column(JSON, default=dict)


class SessionEvent(Base):
    __tablename__ = "session_events"
    __table_args__ = (Index("ix_events_session_time", "session_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("browser_sessions.id"), index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class PerformanceMetric(Base):
    __tablename__ = "performance_metrics"
    __table_args__ = (Index("ix_perf_session_time", "session_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("browser_sessions.id"), index=True)
    route: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ApplicationError(Base):
    __tablename__ = "application_errors"
    __table_args__ = (Index("ix_errors_project_time", "project_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("browser_sessions.id"), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(128), index=True)
    message: Mapped[str] = mapped_column(String(512))
    sanitized_stack: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_file: Mapped[str | None] = mapped_column(String(255), nullable=True)
    line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    column: Mapped[int | None] = mapped_column(Integer, nullable=True)
    route: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DiagnosticAction(Base):
    __tablename__ = "diagnostic_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("browser_sessions.id"), index=True)
    requested_by_admin_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True)
    action_type: Mapped[str] = mapped_column(String(64))
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[ActionStatus] = mapped_column(Enum(ActionStatus), default=ActionStatus.PENDING)
    user_visible_description: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DiagnosticResult(Base):
    __tablename__ = "diagnostic_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action_id: Mapped[int] = mapped_column(ForeignKey("diagnostic_actions.id"), index=True)
    status: Mapped[str] = mapped_column(String(32))
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    color: Mapped[str] = mapped_column(String(16), default="#64748b")


class SessionTag(Base):
    __tablename__ = "session_tags"
    __table_args__ = (UniqueConstraint("session_id", "tag_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("browser_sessions.id"), index=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SessionNote(Base):
    __tablename__ = "session_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("browser_sessions.id"), index=True)
    admin_user_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    rule_type: Mapped[str] = mapped_column(String(80), index=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=900)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    alert_rule_id: Mapped[int | None] = mapped_column(ForeignKey("alert_rules.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="OPEN", index=True)
    severity: Mapped[str] = mapped_column(String(32), default="INFO")
    title: Mapped[str] = mapped_column(String(180))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ConsentRecord(Base):
    __tablename__ = "consent_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    visitor_id: Mapped[int | None] = mapped_column(ForeignKey("browser_visitors.id"), nullable=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("browser_sessions.id"), nullable=True)
    consent_state: Mapped[ConsentState] = mapped_column(Enum(ConsentState))
    consent_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="sdk")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Export(Base):
    __tablename__ = "exports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    admin_user_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True)
    export_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    format: Mapped[str] = mapped_column(String(16), default="json")
    filters: Mapped[dict] = mapped_column(JSON, default=dict)
    signed_url_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DataDeletionRequest(Base):
    __tablename__ = "data_deletion_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    visitor_external_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    requested_by_admin_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SdkVersion(Base):
    __tablename__ = "sdk_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(32), unique=True)
    status: Mapped[str] = mapped_column(String(32), default="CURRENT")
    release_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_user_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(96), index=True)
    target_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result: Mapped[str] = mapped_column(String(32), default="SUCCESS")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
