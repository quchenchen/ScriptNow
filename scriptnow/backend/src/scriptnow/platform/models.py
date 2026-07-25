from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from scriptnow.platform.database import Base


def new_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


class TenantStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


class RefreshTokenStatus(StrEnum):
    ACTIVE = "active"
    USED = "used"


class ProviderStatus(StrEnum):
    CONNECTED = "connected"
    UNCONFIGURED = "unconfigured"
    ERROR = "error"


class ProjectMedium(StrEnum):
    SCRIPT = "script"
    NOVEL = "novel"
    TRANSLATION = "translation"


class ProjectSource(StrEnum):
    ORIGINAL = "original"
    ADAPTATION = "adaptation"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReservationState(StrEnum):
    RESERVED = "reserved"
    FINALIZED = "finalized"
    RELEASED = "released"
    REVERSED = "reversed"


class WorkspaceFileStatus(StrEnum):
    READY = "ready"
    QUARANTINED = "quarantined"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class DistillationStatus(StrEnum):
    RUNNING = "running"
    READY_WITH_GAPS = "ready_with_gaps"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DistillationDecision(StrEnum):
    CANDIDATE = "candidate"
    APPROVED = "approved"
    REJECTED = "rejected"


class NarrativeIndexStatus(StrEnum):
    BUILDING = "building"
    READY = "ready"
    FAILED = "failed"


class TenantModel(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    tier: Mapped[str] = mapped_column(String(32), default="plus")
    status: Mapped[str] = mapped_column(String(32), default=TenantStatus.ACTIVE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class UserModel(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        Index("ix_users_tenant_id_id", "tenant_id", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SessionModel(Base):
    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_tenant_id_id", "tenant_id", "id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    family_id: Mapped[str] = mapped_column(String(36), nullable=False, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=SessionStatus.ACTIVE)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RefreshTokenModel(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
        Index("ix_refresh_tokens_session_id_status", "session_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=RefreshTokenStatus.ACTIVE)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LoginThrottleModel(Base):
    __tablename__ = "login_throttles"

    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    blocked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class TierModel(Base):
    __tablename__ = "tiers"
    __table_args__ = (UniqueConstraint("code", name="uq_tiers_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    monthly_price: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    monthly_token_quota: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ProviderModel(Base):
    __tablename__ = "providers"
    __table_args__ = (UniqueConstraint("key", name="uq_providers_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(32), default=ProviderStatus.UNCONFIGURED)
    credential_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    credential_nonce: Mapped[bytes | None] = mapped_column(LargeBinary)
    credential_key_version: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LanguageModelModel(Base):
    __tablename__ = "language_models"
    __table_args__ = (
        UniqueConstraint("key", name="uq_language_models_key"),
        Index("ix_language_models_provider_enabled", "provider_id", "enabled"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    provider_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("providers.id", ondelete="RESTRICT"), nullable=False
    )
    agentscope_class: Mapped[str] = mapped_column(String(80), nullable=False)
    min_tier_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tiers.id", ondelete="RESTRICT"), nullable=False
    )
    input_price_per_million: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    output_price_per_million: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ImageModelModel(Base):
    __tablename__ = "image_models"
    __table_args__ = (
        UniqueConstraint("key", name="uq_image_models_key"),
        Index("ix_image_models_provider_enabled", "provider_id", "enabled"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    provider_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("providers.id", ondelete="RESTRICT"), nullable=False
    )
    protocol: Mapped[str] = mapped_column(String(40), default="grsai_image2", nullable=False)
    endpoint_path: Mapped[str] = mapped_column(
        String(240), default="/v1/api/generate", nullable=False
    )
    min_tier_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tiers.id", ondelete="RESTRICT"), nullable=False
    )
    price_per_image: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    default_parameters: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AgentTemplateVersionModel(Base):
    __tablename__ = "agent_template_versions"
    __table_args__ = (
        UniqueConstraint("role_key", "version", name="uq_agent_template_role_version"),
        Index("ix_agent_template_role_published", "role_key", "published"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    role_key: Mapped[str] = mapped_column(String(80), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    soul: Mapped[str] = mapped_column(String, nullable=False)
    default_model_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("language_models.id", ondelete="RESTRICT"), nullable=False
    )
    fallback_model_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("language_models.id", ondelete="RESTRICT")
    )
    tool_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    policy: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ToolGroupModel(Base):
    __tablename__ = "tool_groups"
    __table_args__ = (UniqueConstraint("key", name="uq_tool_groups_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    tool_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    min_tier_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tiers.id", ondelete="RESTRICT"), nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AgentToolMountModel(Base):
    __tablename__ = "agent_tool_mounts"
    __table_args__ = (UniqueConstraint("role_key", "tool_group_id", name="uq_agent_tool_mount"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    role_key: Mapped[str] = mapped_column(String(80), nullable=False)
    tool_group_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tool_groups.id", ondelete="CASCADE"), nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class McpServerModel(Base):
    __tablename__ = "mcp_servers"
    __table_args__ = (UniqueConstraint("key", name="uq_mcp_servers_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    transport: Mapped[str] = mapped_column(String(32), nullable=False)
    public_config: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    secret_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    secret_nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    secret_key_version: Mapped[int] = mapped_column(Integer, nullable=False)
    min_tier_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tiers.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), default="unconfigured")
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    confirmation_required: Mapped[bool] = mapped_column(Boolean, default=True)
    last_error: Mapped[str | None] = mapped_column(String(500))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class McpToolModel(Base):
    __tablename__ = "mcp_tools"
    __table_args__ = (UniqueConstraint("server_id", "key", name="uq_mcp_tool_server_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    server_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("mcp_servers.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(160), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), default="")
    whitelisted: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class SandboxPolicyModel(Base):
    __tablename__ = "sandbox_policies"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class TenantAgentConfigModel(Base):
    __tablename__ = "tenant_agent_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_id", "role_key", name="uq_tenant_agent_config"),
        Index("ix_tenant_agent_config_project", "tenant_id", "project_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    role_key: Mapped[str] = mapped_column(String(80), nullable=False)
    custom_name: Mapped[str | None] = mapped_column(String(80))
    soul_override: Mapped[str | None] = mapped_column(String(2000))
    model_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("language_models.id", ondelete="RESTRICT")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class RuntimeConfigSnapshotModel(Base):
    __tablename__ = "runtime_config_snapshots"
    __table_args__ = (UniqueConstraint("run_id", name="uq_runtime_config_snapshot_run"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    template_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_template_versions.id", ondelete="RESTRICT"), nullable=False
    )
    snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ProjectModel(Base):
    __tablename__ = "projects"
    __table_args__ = (Index("ix_projects_tenant_id_id", "tenant_id", "id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    medium: Mapped[str] = mapped_column(String(32), nullable=False)
    source_mode: Mapped[str] = mapped_column(String(32), default=ProjectSource.ORIGINAL)
    direction: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class WorkPackageModel(Base):
    """User-facing publication metadata derived from adopted project facts."""

    __tablename__ = "work_packages"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_work_package_version"),
        Index("ix_work_packages_tenant_project", "tenant_id", "project_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    synopsis: Mapped[str] = mapped_column(String, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    language: Mapped[str] = mapped_column(String(32), nullable=False)
    cover_brief: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    cover_prompt: Mapped[str] = mapped_column(String, nullable=False)
    feedback: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CoverArtifactModel(Base):
    __tablename__ = "cover_artifacts"
    __table_args__ = (Index("ix_cover_artifacts_tenant_project", "tenant_id", "project_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    work_package_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("work_packages.id", ondelete="RESTRICT"), nullable=False
    )
    image_model_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("image_models.id", ondelete="RESTRICT"), nullable=False
    )
    provider_request_id: Mapped[str] = mapped_column(String(240), nullable=False)
    image_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    prompt_snapshot: Mapped[str] = mapped_column(String, nullable=False)
    platform_key: Mapped[str] = mapped_column(String(40), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    language: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="candidate", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ProjectSnapshotModel(Base):
    """Platform snapshot metadata; domain content remains in separate domain tables."""

    __tablename__ = "project_snapshots"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_project_snapshot_version"),
        Index("ix_project_snapshots_tenant_project", "tenant_id", "project_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    medium: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    trigger: Mapped[str] = mapped_column(String(32), default="manual")
    scope: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    base_snapshot_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("project_snapshots.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ProjectRunModel(Base):
    __tablename__ = "project_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_project_runs_idempotency"),
        Index("ix_project_runs_tenant_project", "tenant_id", "project_id"),
        Index("ix_project_runs_status_updated", "status", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=RunStatus.QUEUED)
    waiting_reason: Mapped[str | None] = mapped_column(String(120))
    error_code: Mapped[str | None] = mapped_column(String(120))
    state_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ProjectEventModel(Base):
    __tablename__ = "project_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_project_events_run_sequence"),
        UniqueConstraint("run_id", "event_key", name="uq_project_events_run_key"),
        UniqueConstraint("stream_key", "sequence", name="uq_project_events_stream_sequence"),
        UniqueConstraint("stream_key", "event_key", name="uq_project_events_stream_key"),
        Index("ix_project_events_tenant_run_sequence", "tenant_id", "run_id", "sequence"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("project_runs.id", ondelete="CASCADE")
    )
    stream_key: Mapped[str] = mapped_column(String(100), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_key: Mapped[str] = mapped_column(String(160), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    actor: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    aggregate: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    causation_id: Mapped[str | None] = mapped_column(String(120))
    correlation_id: Mapped[str] = mapped_column(String(120), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


@event.listens_for(ProjectEventModel, "before_update")
@event.listens_for(ProjectEventModel, "before_delete")
def reject_project_event_mutation(*_: object) -> None:
    raise ValueError("project events are append-only")


class RunStreamEventModel(Base):
    __tablename__ = "run_stream_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_run_stream_sequence"),
        UniqueConstraint("run_id", "event_key", name="uq_run_stream_event_key"),
        Index("ix_run_stream_tenant_run_sequence", "tenant_id", "run_id", "sequence"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("project_runs.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_key: Mapped[str] = mapped_column(String(160), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(120), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


@event.listens_for(RunStreamEventModel, "before_update")
@event.listens_for(RunStreamEventModel, "before_delete")
def reject_run_stream_event_mutation(*_: object) -> None:
    raise ValueError("run stream events are append-only")


class TokenAccountModel(Base):
    __tablename__ = "token_accounts"
    __table_args__ = (UniqueConstraint("tenant_id", "tier", name="uq_token_accounts_scope"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    tier: Mapped[str] = mapped_column(String(32), nullable=False)
    period_key: Mapped[str] = mapped_column(String(20), nullable=False)
    monthly_available: Mapped[int] = mapped_column(Integer, default=0)
    credits_available: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class UsageReservationModel(Base):
    __tablename__ = "usage_reservations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_usage_reservation_idempotency"),
        Index("ix_usage_reservations_run", "run_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("project_runs.id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    tier: Mapped[str] = mapped_column(String(32), nullable=False)
    period_key: Mapped[str] = mapped_column(String(20), nullable=False)
    monthly_reserved: Mapped[int] = mapped_column(Integer, nullable=False)
    credits_reserved: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_tokens: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default=ReservationState.RESERVED)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TokenUsageModel(Base):
    __tablename__ = "token_usage"
    __table_args__ = (
        UniqueConstraint("run_id", "framework_event_id", name="uq_token_usage_event"),
        Index("ix_token_usage_tenant_project", "tenant_id", "project_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    reservation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("usage_reservations.id", ondelete="RESTRICT"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("project_runs.id", ondelete="RESTRICT"), nullable=False
    )
    framework_event_id: Mapped[str] = mapped_column(String(160), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_role: Mapped[str] = mapped_column(String(80), nullable=False)
    model_key: Mapped[str] = mapped_column(String(120), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    input_price_per_million: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    output_price_per_million: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    cost_estimate: Mapped[float] = mapped_column(Numeric(14, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CreditLedgerModel(Base):
    __tablename__ = "credit_ledger"
    __table_args__ = (
        UniqueConstraint("reservation_id", "operation", name="uq_credit_ledger_operation"),
        Index("ix_credit_ledger_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    reservation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("usage_reservations.id", ondelete="RESTRICT")
    )
    reference_key: Mapped[str | None] = mapped_column(String(120), unique=True)
    run_id: Mapped[str] = mapped_column(String(120), nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    tier: Mapped[str] = mapped_column(String(32), nullable=False)
    period_key: Mapped[str] = mapped_column(String(20), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    monthly_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    credits_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    monthly_before: Mapped[int] = mapped_column(Integer, nullable=False)
    monthly_after: Mapped[int] = mapped_column(Integer, nullable=False)
    credits_before: Mapped[int] = mapped_column(Integer, nullable=False)
    credits_after: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_tokens: Mapped[int | None] = mapped_column(Integer)
    reversal_of_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("credit_ledger.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


@event.listens_for(CreditLedgerModel, "before_update")
@event.listens_for(CreditLedgerModel, "before_delete")
def reject_credit_ledger_mutation(*_: object) -> None:
    raise ValueError("credit ledger is append-only")


class OrderModel(Base):
    __tablename__ = "orders"
    __table_args__ = (Index("ix_orders_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    tier: Mapped[str] = mapped_column(String(32), nullable=False)
    token_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    note: Mapped[str] = mapped_column(String(500), default="")
    actor_id: Mapped[str] = mapped_column(String(120), nullable=False)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


@event.listens_for(OrderModel, "before_update")
@event.listens_for(OrderModel, "before_delete")
def reject_order_mutation(*_: object) -> None:
    raise ValueError("orders are append-only")


class WorkspaceFileModel(Base):
    __tablename__ = "workspace_files"
    __table_args__ = (
        Index("ix_workspace_files_tenant_project", "tenant_id", "project_id"),
        UniqueConstraint("project_id", "storage_name", name="uq_workspace_file_storage_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_name: Mapped[str] = mapped_column(String(100), nullable=False)
    media_type: Mapped[str] = mapped_column(String(120), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuditLogModel(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(120), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    correlation_id: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


@event.listens_for(AuditLogModel, "before_update")
@event.listens_for(AuditLogModel, "before_delete")
def reject_audit_log_mutation(*_: object) -> None:
    raise ValueError("audit log is append-only")


class AgentStateModel(Base):
    __tablename__ = "agent_states"
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_id", "role_key", name="uq_agent_state_scope"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    role_key: Mapped[str] = mapped_column(String(80), nullable=False)
    serialized_state: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    context_tokens: Mapped[int | None] = mapped_column(Integer)
    context_limit: Mapped[int | None] = mapped_column(Integer)
    state_version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class MemoryEntryModel(Base):
    __tablename__ = "memory_entries"
    __table_args__ = (Index("ix_memory_entries_scope", "tenant_id", "project_id", "role_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    role_key: Mapped[str] = mapped_column(String(80), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class MemoryPolicyModel(Base):
    __tablename__ = "memory_policies"

    role_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    memory_max_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger_ratio: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    reserve_ratio: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    memory_instructions: Mapped[str] = mapped_column(String(4000), nullable=False)
    preserve_creative_decisions: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class MemoryAuditModel(Base):
    __tablename__ = "memory_audit"
    __table_args__ = (Index("ix_memory_audit_scope", "tenant_id", "project_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    memory_entry_id: Mapped[str] = mapped_column(String(36), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(120), nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    before_hash: Mapped[str | None] = mapped_column(String(64))
    after_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


@event.listens_for(MemoryAuditModel, "before_update")
@event.listens_for(MemoryAuditModel, "before_delete")
def reject_memory_audit_mutation(*_: object) -> None:
    raise ValueError("memory audit is append-only")


class RagChunkModel(Base):
    __tablename__ = "rag_chunks"
    __table_args__ = (Index("ix_rag_chunks_scope", "tenant_id", "project_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    source_file_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspace_files.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class SourceDistillationModel(Base):
    """Resumable multi-pass analysis of project source material."""

    __tablename__ = "source_distillations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_source_distillation_key"),
        Index("ix_source_distillation_project", "tenant_id", "project_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    source_file_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=DistillationStatus.RUNNING, nullable=False
    )
    pass_key: Mapped[str] = mapped_column(String(40), default="inventory", nullable=False)
    checkpoint: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    coverage: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class SourceEvidenceModel(Base):
    """Atomic, cited evidence extracted during a distillation run."""

    __tablename__ = "source_evidence"
    __table_args__ = (
        UniqueConstraint("distillation_id", "evidence_key", name="uq_source_evidence_key"),
        Index("ix_source_evidence_run_dimension", "distillation_id", "dimension"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    distillation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("source_distillations.id", ondelete="CASCADE"), nullable=False
    )
    evidence_key: Mapped[str] = mapped_column(String(160), nullable=False)
    source_file_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspace_files.id", ondelete="RESTRICT"), nullable=False
    )
    chunk_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rag_chunks.id", ondelete="RESTRICT"), nullable=False
    )
    source_unit: Mapped[str] = mapped_column(String(240), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    dimension: Mapped[str] = mapped_column(String(60), nullable=False)
    claim: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False)
    inference: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    related_evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    contradiction_group: Mapped[str | None] = mapped_column(String(120))
    extraction_pass: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SourceProfileModel(Base):
    """Versioned candidate or approved creative profile derived from cited evidence."""

    __tablename__ = "source_profiles"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_source_profile_version"),
        Index("ix_source_profiles_project_decision", "tenant_id", "project_id", "decision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    distillation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("source_distillations.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(
        String(32), default=DistillationDecision.CANDIDATE, nullable=False
    )
    profile: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    conflicts: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list, nullable=False)
    exclusions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    decision_feedback: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NarrativeIndexModel(Base):
    """Versioned, source-grounded index for a single novel manuscript."""

    __tablename__ = "narrative_indexes"
    __table_args__ = (
        UniqueConstraint("source_file_id", "version", name="uq_narrative_index_version"),
        Index("ix_narrative_index_project", "tenant_id", "project_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    source_file_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspace_files.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=NarrativeIndexStatus.BUILDING, nullable=False
    )
    config: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class NarrativeTextUnitModel(Base):
    """A semantic manuscript unit that never crosses a detected chapter boundary."""

    __tablename__ = "narrative_text_units"
    __table_args__ = (
        UniqueConstraint("index_id", "ordinal", name="uq_narrative_unit_ordinal"),
        Index("ix_narrative_unit_chapter", "index_id", "chapter_key", "ordinal"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    index_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("narrative_indexes.id", ondelete="CASCADE"), nullable=False
    )
    source_file_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspace_files.id", ondelete="RESTRICT"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    chapter_key: Mapped[str] = mapped_column(String(120), nullable=False)
    chapter_title: Mapped[str] = mapped_column(String(300), nullable=False)
    unit_type: Mapped[str] = mapped_column(String(40), default="passage", nullable=False)
    start_char: Mapped[int] = mapped_column(Integer, nullable=False)
    end_char: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    contextual_header: Mapped[str] = mapped_column(String(500), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class NarrativeNodeModel(Base):
    """Canonical entity, event, promise, rule, or state in the narrative graph."""

    __tablename__ = "narrative_nodes"
    __table_args__ = (
        UniqueConstraint("index_id", "node_key", name="uq_narrative_node_key"),
        Index("ix_narrative_node_type", "index_id", "node_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    index_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("narrative_indexes.id", ondelete="CASCADE"), nullable=False
    )
    node_key: Mapped[str] = mapped_column(String(160), nullable=False)
    node_type: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    attributes: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    evidence_unit_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)


class NarrativeEdgeModel(Base):
    """Typed, multi-source relationship between two canonical narrative nodes."""

    __tablename__ = "narrative_edges"
    __table_args__ = (
        UniqueConstraint("index_id", "edge_key", name="uq_narrative_edge_key"),
        Index("ix_narrative_edge_nodes", "index_id", "source_node_id", "target_node_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    index_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("narrative_indexes.id", ondelete="CASCADE"), nullable=False
    )
    edge_key: Mapped[str] = mapped_column(String(180), nullable=False)
    edge_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_node_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("narrative_nodes.id", ondelete="CASCADE"), nullable=False
    )
    target_node_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("narrative_nodes.id", ondelete="CASCADE"), nullable=False
    )
    description: Mapped[str] = mapped_column(String, nullable=False)
    evidence_unit_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False)
    inference: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class NarrativeSummaryModel(Base):
    """A chapter, cluster, volume, or work summary with explicit child provenance."""

    __tablename__ = "narrative_summaries"
    __table_args__ = (
        UniqueConstraint("index_id", "summary_key", name="uq_narrative_summary_key"),
        Index("ix_narrative_summary_level", "index_id", "level"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    index_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("narrative_indexes.id", ondelete="CASCADE"), nullable=False
    )
    summary_key: Mapped[str] = mapped_column(String(180), nullable=False)
    level: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    child_unit_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    child_summary_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    evidence_node_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
