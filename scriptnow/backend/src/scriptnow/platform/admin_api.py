from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Cookie, Header, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, or_, select

from scriptnow.platform.audit import AuditService
from scriptnow.platform.auth import AuthenticationFailed, AuthService, CsrfFailed
from scriptnow.platform.auth_api import ACCESS_COOKIE
from scriptnow.platform.config import Settings
from scriptnow.platform.database import Database
from scriptnow.platform.mcp_governance import McpGovernanceError, McpGovernanceService
from scriptnow.platform.memory import MemoryError, MemoryService
from scriptnow.platform.model_supply import (
    CredentialCipher,
    CredentialError,
    ModelSupplyService,
    ProviderDiscoveryError,
)
from scriptnow.platform.models import (
    AgentTemplateVersionModel,
    AgentToolMountModel,
    CreditLedgerModel,
    ImageModelModel,
    LanguageModelModel,
    McpServerModel,
    McpToolModel,
    MemoryAuditModel,
    MemoryEntryModel,
    MemoryPolicyModel,
    OrderModel,
    ProjectModel,
    ProjectRunModel,
    ProviderModel,
    RuntimeConfigSnapshotModel,
    SandboxPolicyModel,
    TenantAgentConfigModel,
    TenantModel,
    TenantStatus,
    TierModel,
    TokenAccountModel,
    TokenUsageModel,
    ToolGroupModel,
    UsageReservationModel,
    UserModel,
)
from scriptnow.platform.skills import (
    ROLE_SKILLS,
    SkillCatalog,
    SkillCatalogError,
    SkillConflictError,
)


class AdminOverviewResponse(BaseModel):
    total_tenants: int
    active_tenants: int
    exhausted_tenants: int
    total_tokens: int


class AdminSkillDetailResponse(BaseModel):
    name: str
    description: str
    domain: str
    references: list[str]
    digest: str
    instructions: str
    roles: list[str]
    stages: list[str]
    genres: list[str]
    themes: list[str]
    styles: list[str]
    structures: list[str]
    selection_priority: int
    admission_status: str
    admission_baseline: str | None
    admission_cases: list[str]
    quality_status: str
    benchmark_suite: str | None
    benchmark_report: str | None


class AdminSkillUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(min_length=1, max_length=1000)
    instructions: str = Field(min_length=1, max_length=100_000)
    expected_digest: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")


class AdminTenantResponse(BaseModel):
    id: str
    name: str
    owner_email: str
    tier: str
    tier_name: str
    status: str
    monthly_used: int
    monthly_quota: int
    credits_available: int
    created_at: str


class AdminTenantPageResponse(BaseModel):
    items: list[AdminTenantResponse]
    total: int
    limit: int
    offset: int


class AdminTierResponse(BaseModel):
    code: str
    name: str
    rank: int
    monthly_price: float
    monthly_token_quota: int
    enabled: bool
    version: int


class AdminCreateTenantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    owner_email: str = Field(min_length=3, max_length=320)
    temporary_password: str = Field(min_length=12, max_length=200)
    tier: str = Field(min_length=1, max_length=32)


class AdminTierChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tier: str = Field(min_length=1, max_length=32)
    note: str = Field(min_length=1, max_length=500)


class AdminGrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tier: str = Field(min_length=1, max_length=32)
    tokens: int = Field(ge=1, le=10_000_000)
    note: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=50)


class AdminGrantResponse(BaseModel):
    order_id: str
    tenant_id: str
    tier: str
    granted_tokens: int
    credits_available: int
    idempotent: bool


class AdminStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: TenantStatus


class AdminUsageSummaryResponse(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost: float
    currency: str


class AdminUsageRunResponse(BaseModel):
    run_id: str
    trace_id: str
    trace_url: str | None
    tenant_name: str
    project_name: str
    status: str
    agent_role: str
    model_key: str
    input_tokens: int
    output_tokens: int
    reserved_tokens: int
    budget_variance_tokens: int
    budget_utilization: float
    budget_status: str
    estimated_cost: float
    currency: str
    input_price_per_million: float
    output_price_per_million: float
    is_mock: bool
    created_at: str


class AdminUsagePageResponse(BaseModel):
    summary: AdminUsageSummaryResponse
    items: list[AdminUsageRunResponse]
    total: int
    limit: int
    offset: int


class AdminProviderResponse(BaseModel):
    id: str
    key: str
    name: str
    base_url: str | None
    status: str
    credential_configured: bool


class AdminProviderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    base_url: str | None = Field(default=None, max_length=1000)
    credential: str = Field(min_length=1, max_length=4000)


class AdminDiscoveredModelResponse(BaseModel):
    key: str
    display_name: str


class AdminModelResponse(BaseModel):
    id: str
    key: str
    display_name: str
    provider_id: str
    provider_name: str
    provider_status: str
    agentscope_class: str
    min_tier_code: str
    min_tier_name: str
    input_price_per_million: float
    output_price_per_million: float
    context_window: int
    enabled: bool
    version: int


class AdminModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9._:/-]+$")
    display_name: str = Field(min_length=1, max_length=160)
    provider_id: str = Field(min_length=1, max_length=36)
    agentscope_class: str = Field(min_length=1, max_length=80)
    min_tier_code: str = Field(min_length=1, max_length=32)
    input_price_per_million: float = Field(ge=0, le=1_000_000)
    output_price_per_million: float = Field(ge=0, le=1_000_000)
    context_window: int = Field(default=32_768, ge=1_024, le=10_000_000)
    enabled: bool = True


class AdminImageModelResponse(BaseModel):
    id: str
    key: str
    display_name: str
    provider_id: str
    provider_name: str
    provider_status: str
    protocol: str
    endpoint_path: str
    min_tier_code: str
    min_tier_name: str
    price_per_image: float
    default_parameters: dict[str, object]
    enabled: bool
    version: int


class AdminImageModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9._:/-]+$")
    display_name: str = Field(min_length=1, max_length=160)
    provider_id: str = Field(min_length=1, max_length=36)
    protocol: str = Field(default="grsai_image2", pattern=r"^grsai_image2$")
    endpoint_path: str = Field(default="/v1/api/generate", pattern=r"^/[a-zA-Z0-9_./-]+$")
    min_tier_code: str = Field(min_length=1, max_length=32)
    price_per_image: float = Field(ge=0, le=1_000_000)
    default_parameters: dict[str, object] = Field(default_factory=dict)
    enabled: bool = True


class AdminTierUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    rank: int = Field(ge=0, le=10_000)
    monthly_price: float = Field(ge=0, le=1_000_000)
    monthly_token_quota: int = Field(ge=0, le=1_000_000_000)
    enabled: bool


class AdminSupplyResponse(BaseModel):
    providers: list[AdminProviderResponse]
    models: list[AdminModelResponse]
    image_models: list[AdminImageModelResponse]
    tiers: list[AdminTierResponse]


class AdminAgentTemplateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role_key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_-]+$")
    soul: str = Field(min_length=1, max_length=20_000)
    default_model_id: str = Field(min_length=36, max_length=36)
    fallback_model_id: str | None = Field(default=None, min_length=36, max_length=36)
    tool_keys: list[str] = Field(default_factory=list, max_length=100)
    policy: dict[str, object] = Field(default_factory=dict)


class AdminAgentTemplateResponse(BaseModel):
    id: str
    role_key: str
    version: int
    soul: str
    default_model_id: str
    fallback_model_id: str | None
    tool_keys: list[str]
    policy: dict[str, object]
    published: bool


class AdminToolGroupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9_.-]+$")
    name: str = Field(min_length=1, max_length=160)
    tool_keys: list[str] = Field(min_length=1, max_length=100)
    min_tier_code: str = Field(min_length=1, max_length=32)
    enabled: bool = True


class AdminToolMountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role_key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_-]+$")
    tool_group_id: str = Field(min_length=36, max_length=36)
    enabled: bool = True


class AdminCapabilitiesResponse(BaseModel):
    templates: list[AdminAgentTemplateResponse]
    tool_groups: list[dict[str, object]]
    mounts: list[dict[str, object]]
    skill_plans: list[dict[str, object]]


class AdminMcpServerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=160)
    transport: str = Field(pattern=r"^(http|stdio)$")
    config: dict[str, object]
    min_tier_code: str = Field(min_length=1, max_length=32)
    enabled: bool = True
    confirmation_required: bool = True


class AdminMcpWhitelistRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    whitelisted: bool


class AdminSandboxRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str = Field(pattern=r"^(direct|sandbox|sandbox_confirm)$")


class AdminMemoryContentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=100_000)


class AdminMemoryPolicyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    memory_max_tokens: int = Field(ge=100, le=1_000_000)
    trigger_ratio: float = Field(gt=0, le=1)
    reserve_ratio: float = Field(ge=0, lt=1)
    memory_instructions: str = Field(min_length=1, max_length=4000)
    preserve_creative_decisions: bool = True


def create_admin_router(database: Database, auth: AuthService, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/admin/api", tags=["admin"])
    skills = SkillCatalog(Path(__file__).parents[3] / "skills")
    audit = AuditService(database)
    supply = ModelSupplyService(
        database,
        CredentialCipher(lambda version: settings.credential_master_key),
        key_version=settings.credential_key_version,
    )
    mcp = McpGovernanceService(
        database,
        CredentialCipher(lambda version: settings.credential_master_key),
        key_version=settings.credential_key_version,
    )
    memories = MemoryService(database, Path(settings.workspace_root))

    async def admin_context(access_token: str | None):
        if access_token is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
        try:
            context = await auth.validate_access(access_token)
        except AuthenticationFailed as error:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required") from error
        if not context.is_admin:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "administrator role required")
        return context

    async def admin_action(access_token: str | None, csrf_token: str | None):
        if access_token is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
        if csrf_token is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "csrf token required")
        try:
            context = await auth.authorize_action(access_token, csrf_token)
        except CsrfFailed as error:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "csrf validation failed") from error
        except AuthenticationFailed as error:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required") from error
        if not context.is_admin:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "administrator role required")
        return context

    @router.get("/skills")
    async def skill_catalog(
        domain: str | None = Query(default=None, pattern=r"^(platform|novel|script)$"),
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> dict[str, object]:
        await admin_context(access_token)
        catalog = skills.for_domain(domain) if domain else skills.scan()
        return {
            "skills": [
                {
                    "name": item.name,
                    "description": item.description,
                    "domain": item.domain,
                    "references": list(item.references),
                    "digest": item.digest,
                    "roles": list(item.roles),
                    "stages": list(item.stages),
                    "genres": list(item.genres),
                    "themes": list(item.themes),
                    "styles": list(item.styles),
                    "structures": list(item.structures),
                    "selection_priority": item.selection_priority,
                    "admission_status": item.admission_status,
                    "admission_baseline": item.admission_baseline,
                    "admission_cases": list(item.admission_cases),
                    "quality_status": item.quality_status,
                    "benchmark_suite": item.benchmark_suite,
                    "benchmark_report": item.benchmark_report,
                }
                for item in catalog
            ],
            "mounted_by_role": {
                role: [*keys, "project-diagnose"] for role, keys in ROLE_SKILLS.items()
            },
        }

    @router.get("/skills/{skill_name}", response_model=AdminSkillDetailResponse)
    async def skill_detail(
        skill_name: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> AdminSkillDetailResponse:
        await admin_context(access_token)
        try:
            descriptor, instructions = skills.detail(skill_name)
        except SkillCatalogError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        return AdminSkillDetailResponse(
            name=descriptor.name,
            description=descriptor.description,
            domain=descriptor.domain,
            references=list(descriptor.references),
            digest=descriptor.digest,
            instructions=instructions,
            roles=list(descriptor.roles),
            stages=list(descriptor.stages),
            genres=list(descriptor.genres),
            themes=list(descriptor.themes),
            styles=list(descriptor.styles),
            structures=list(descriptor.structures),
            selection_priority=descriptor.selection_priority,
            admission_status=descriptor.admission_status,
            admission_baseline=descriptor.admission_baseline,
            admission_cases=list(descriptor.admission_cases),
            quality_status=descriptor.quality_status,
            benchmark_suite=descriptor.benchmark_suite,
            benchmark_report=descriptor.benchmark_report,
        )

    @router.put("/skills/{skill_name}", response_model=AdminSkillDetailResponse)
    async def update_skill(
        skill_name: str,
        body: AdminSkillUpdateRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AdminSkillDetailResponse:
        context = await admin_action(access_token, csrf_token)
        try:
            descriptor = skills.update(
                name=skill_name,
                description=body.description,
                instructions=body.instructions,
                expected_digest=body.expected_digest,
            )
            _, instructions = skills.detail(skill_name)
        except SkillConflictError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        except SkillCatalogError as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
        await audit.record(
            tenant_id=str(context.tenant_id),
            actor_id=str(context.user_id),
            action="skill.update",
            resource_type="skill",
            resource_id=skill_name,
            outcome="succeeded",
            correlation_id=descriptor.digest,
            details={"domain": descriptor.domain, "digest": descriptor.digest},
        )
        return AdminSkillDetailResponse(
            name=descriptor.name,
            description=descriptor.description,
            domain=descriptor.domain,
            references=list(descriptor.references),
            digest=descriptor.digest,
            instructions=instructions,
            roles=list(descriptor.roles),
            stages=list(descriptor.stages),
            genres=list(descriptor.genres),
            themes=list(descriptor.themes),
            styles=list(descriptor.styles),
            structures=list(descriptor.structures),
            selection_priority=descriptor.selection_priority,
            admission_status=descriptor.admission_status,
            admission_baseline=descriptor.admission_baseline,
            admission_cases=list(descriptor.admission_cases),
            quality_status=descriptor.quality_status,
            benchmark_suite=descriptor.benchmark_suite,
            benchmark_report=descriptor.benchmark_report,
        )

    @router.get("/overview", response_model=AdminOverviewResponse)
    async def overview(
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> AdminOverviewResponse:
        await admin_context(access_token)
        async with database.session() as session:
            tenants = list((await session.scalars(select(TenantModel))).all())
            accounts = list((await session.scalars(select(TokenAccountModel))).all())
            total_tokens = int(
                await session.scalar(
                    select(
                        func.coalesce(
                            func.sum(TokenUsageModel.input_tokens + TokenUsageModel.output_tokens),
                            0,
                        )
                    )
                )
                or 0
            )
        active = sum(item.status == TenantStatus.ACTIVE for item in tenants)
        exhausted = sum(item.monthly_available + item.credits_available <= 0 for item in accounts)
        return AdminOverviewResponse(
            total_tenants=len(tenants),
            active_tenants=active,
            exhausted_tenants=exhausted,
            total_tokens=total_tokens,
        )

    @router.get("/tenants", response_model=AdminTenantPageResponse)
    async def tenants(
        search: Annotated[str, Query(max_length=160)] = "",
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> AdminTenantPageResponse:
        await admin_context(access_token)
        async with database.session() as session:
            query = select(TenantModel)
            normalized = search.strip()
            if normalized:
                owner_tenants = select(UserModel.tenant_id).where(
                    UserModel.email.ilike(f"%{normalized}%")
                )
                query = query.where(
                    or_(
                        TenantModel.name.ilike(f"%{normalized}%"), TenantModel.id.in_(owner_tenants)
                    )
                )
            total = int(
                await session.scalar(select(func.count()).select_from(query.subquery())) or 0
            )
            rows = list(
                (
                    await session.scalars(
                        query.order_by(TenantModel.created_at.desc()).offset(offset).limit(limit)
                    )
                ).all()
            )
            tenant_ids = [item.id for item in rows]
            users = list(
                (
                    await session.scalars(
                        select(UserModel)
                        .where(UserModel.tenant_id.in_(tenant_ids))
                        .order_by(UserModel.created_at)
                    )
                ).all()
            )
            owners = {}
            for user in users:
                owners.setdefault(user.tenant_id, user.email)
            tiers = {item.code: item for item in (await session.scalars(select(TierModel))).all()}
            accounts = {
                (item.tenant_id, item.tier): item
                for item in (
                    await session.scalars(
                        select(TokenAccountModel).where(TokenAccountModel.tenant_id.in_(tenant_ids))
                    )
                ).all()
            }
            items = []
            for tenant in rows:
                tier = tiers.get(tenant.tier)
                account = accounts.get((tenant.id, tenant.tier))
                quota = tier.monthly_token_quota if tier else 0
                remaining = account.monthly_available if account else 0
                items.append(
                    AdminTenantResponse(
                        id=tenant.id,
                        name=tenant.name,
                        owner_email=owners.get(tenant.id, "—"),
                        tier=tenant.tier,
                        tier_name=tier.name if tier else tenant.tier,
                        status=tenant.status,
                        monthly_used=max(0, quota - remaining),
                        monthly_quota=quota,
                        credits_available=account.credits_available if account else 0,
                        created_at=tenant.created_at.isoformat(),
                    )
                )
        return AdminTenantPageResponse(items=items, total=total, limit=limit, offset=offset)

    @router.get("/tiers", response_model=list[AdminTierResponse])
    async def tiers(
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> list[AdminTierResponse]:
        await admin_context(access_token)
        async with database.session() as session:
            rows = list(
                (
                    await session.scalars(
                        select(TierModel)
                        .where(TierModel.enabled.is_(True))
                        .order_by(TierModel.rank)
                    )
                ).all()
            )
        return [
            AdminTierResponse(
                code=item.code,
                name=item.name,
                rank=item.rank,
                monthly_price=float(item.monthly_price),
                monthly_token_quota=item.monthly_token_quota,
                enabled=item.enabled,
                version=item.version,
            )
            for item in rows
        ]

    @router.get("/supply", response_model=AdminSupplyResponse)
    async def supply_overview(
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> AdminSupplyResponse:
        await admin_context(access_token)
        async with database.session() as session:
            providers = list(
                (await session.scalars(select(ProviderModel).order_by(ProviderModel.name))).all()
            )
            tiers = list((await session.scalars(select(TierModel).order_by(TierModel.rank))).all())
            rows = (
                await session.execute(
                    select(LanguageModelModel, ProviderModel, TierModel)
                    .join(ProviderModel, ProviderModel.id == LanguageModelModel.provider_id)
                    .join(TierModel, TierModel.id == LanguageModelModel.min_tier_id)
                    .order_by(LanguageModelModel.display_name)
                )
            ).all()
            image_rows = (
                await session.execute(
                    select(ImageModelModel, ProviderModel, TierModel)
                    .join(ProviderModel, ProviderModel.id == ImageModelModel.provider_id)
                    .join(TierModel, TierModel.id == ImageModelModel.min_tier_id)
                    .order_by(ImageModelModel.display_name)
                )
            ).all()
        return AdminSupplyResponse(
            providers=[
                AdminProviderResponse(
                    id=item.id,
                    key=item.key,
                    name=item.name,
                    base_url=item.base_url,
                    status=item.status,
                    credential_configured=item.credential_ciphertext is not None,
                )
                for item in providers
            ],
            models=[
                AdminModelResponse(
                    id=model.id,
                    key=model.key,
                    display_name=model.display_name,
                    provider_id=provider.id,
                    provider_name=provider.name,
                    provider_status=provider.status,
                    agentscope_class=model.agentscope_class,
                    min_tier_code=tier.code,
                    min_tier_name=tier.name,
                    input_price_per_million=float(model.input_price_per_million),
                    output_price_per_million=float(model.output_price_per_million),
                    context_window=model.context_window,
                    enabled=model.enabled,
                    version=model.version,
                )
                for model, provider, tier in rows
            ],
            image_models=[
                AdminImageModelResponse(
                    id=model.id,
                    key=model.key,
                    display_name=model.display_name,
                    provider_id=provider.id,
                    provider_name=provider.name,
                    provider_status=provider.status,
                    protocol=model.protocol,
                    endpoint_path=model.endpoint_path,
                    min_tier_code=tier.code,
                    min_tier_name=tier.name,
                    price_per_image=float(model.price_per_image),
                    default_parameters=dict(model.default_parameters),
                    enabled=model.enabled,
                    version=model.version,
                )
                for model, provider, tier in image_rows
            ],
            tiers=[
                AdminTierResponse(
                    code=item.code,
                    name=item.name,
                    rank=item.rank,
                    monthly_price=float(item.monthly_price),
                    monthly_token_quota=item.monthly_token_quota,
                    enabled=item.enabled,
                    version=item.version,
                )
                for item in tiers
            ],
        )

    @router.post("/providers", response_model=AdminProviderResponse)
    async def configure_provider(
        body: AdminProviderRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AdminProviderResponse:
        context = await admin_action(access_token, csrf_token)
        view = await supply.configure_provider(
            key=body.key,
            name=body.name.strip(),
            base_url=body.base_url.strip() if body.base_url else None,
            credential=body.credential,
        )
        await audit.record(
            tenant_id=str(context.tenant_id),
            actor_id=str(context.user_id),
            action="provider.configure",
            resource_type="provider",
            resource_id=view.id,
            outcome="succeeded",
            correlation_id=view.id,
            details={"key": view.key, "credential_reset": True},
        )
        return AdminProviderResponse(
            id=view.id,
            key=view.key,
            name=view.name,
            base_url=view.base_url,
            status=view.status,
            credential_configured=view.credential_configured,
        )

    @router.post(
        "/providers/{provider_id}/discover-models",
        response_model=list[AdminDiscoveredModelResponse],
    )
    async def discover_provider_models(
        provider_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> list[AdminDiscoveredModelResponse]:
        context = await admin_action(access_token, csrf_token)
        try:
            discovered = await supply.discover_models(provider_id)
        except (ProviderDiscoveryError, CredentialError) as error:
            await audit.record(
                tenant_id=str(context.tenant_id),
                actor_id=str(context.user_id),
                action="provider.models.discover",
                resource_type="provider",
                resource_id=provider_id,
                outcome="failed",
                correlation_id=provider_id,
                details={"error": str(error)},
            )
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error
        await audit.record(
            tenant_id=str(context.tenant_id),
            actor_id=str(context.user_id),
            action="provider.models.discover",
            resource_type="provider",
            resource_id=provider_id,
            outcome="succeeded",
            correlation_id=provider_id,
            details={"model_count": len(discovered)},
        )
        return [
            AdminDiscoveredModelResponse(key=item.key, display_name=item.display_name)
            for item in discovered
        ]

    @router.delete("/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_provider(
        provider_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> None:
        context = await admin_action(access_token, csrf_token)
        async with database.session() as session:
            provider = await session.get(ProviderModel, provider_id)
            if provider is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "provider not found")
            model_ids = list(
                (
                    await session.scalars(
                        select(LanguageModelModel.id).where(
                            LanguageModelModel.provider_id == provider_id
                        )
                    )
                ).all()
            )
            image_model_ids = list(
                (
                    await session.scalars(
                        select(ImageModelModel.id).where(ImageModelModel.provider_id == provider_id)
                    )
                ).all()
            )
            if model_ids:
                template_refs = int(
                    await session.scalar(
                        select(func.count())
                        .select_from(AgentTemplateVersionModel)
                        .where(
                            or_(
                                AgentTemplateVersionModel.default_model_id.in_(model_ids),
                                AgentTemplateVersionModel.fallback_model_id.in_(model_ids),
                            )
                        )
                    )
                    or 0
                )
                project_refs = int(
                    await session.scalar(
                        select(func.count())
                        .select_from(TenantAgentConfigModel)
                        .where(TenantAgentConfigModel.model_id.in_(model_ids))
                    )
                    or 0
                )
                if template_refs or project_refs:
                    raise HTTPException(
                        status.HTTP_409_CONFLICT,
                        f"Provider 无法删除：{template_refs} 个 Agent 模板、{project_refs} 个项目配置仍在引用其模型",
                    )
                await session.execute(
                    delete(LanguageModelModel).where(LanguageModelModel.id.in_(model_ids))
                )
            if image_model_ids:
                await session.execute(
                    delete(ImageModelModel).where(ImageModelModel.id.in_(image_model_ids))
                )
            provider_name = provider.name
            await session.delete(provider)
        await audit.record(
            tenant_id=str(context.tenant_id),
            actor_id=str(context.user_id),
            action="provider.delete",
            resource_type="provider",
            resource_id=provider_id,
            outcome="succeeded",
            correlation_id=provider_id,
            details={
                "name": provider_name,
                "deleted_models": len(model_ids),
                "deleted_image_models": len(image_model_ids),
            },
        )

    @router.post("/models", response_model=AdminModelResponse)
    async def configure_model(
        body: AdminModelRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AdminModelResponse:
        context = await admin_action(access_token, csrf_token)
        async with database.session() as session:
            provider = await session.get(ProviderModel, body.provider_id)
            tier = (
                await session.scalars(select(TierModel).where(TierModel.code == body.min_tier_code))
            ).one_or_none()
            if provider is None or tier is None:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY, "provider or tier unavailable"
                )
            model = (
                await session.scalars(
                    select(LanguageModelModel).where(LanguageModelModel.key == body.key)
                )
            ).one_or_none()
            if model is None:
                model = LanguageModelModel(
                    key=body.key,
                    display_name=body.display_name.strip(),
                    provider_id=provider.id,
                    agentscope_class=body.agentscope_class,
                    min_tier_id=tier.id,
                )
                session.add(model)
            else:
                model.version += 1
            model.display_name = body.display_name.strip()
            model.provider_id = provider.id
            model.agentscope_class = body.agentscope_class
            model.min_tier_id = tier.id
            model.input_price_per_million = body.input_price_per_million
            model.output_price_per_million = body.output_price_per_million
            model.context_window = body.context_window
            model.enabled = body.enabled
            await session.flush()
            response = AdminModelResponse(
                id=model.id,
                key=model.key,
                display_name=model.display_name,
                provider_id=provider.id,
                provider_name=provider.name,
                provider_status=provider.status,
                agentscope_class=model.agentscope_class,
                min_tier_code=tier.code,
                min_tier_name=tier.name,
                input_price_per_million=float(model.input_price_per_million),
                output_price_per_million=float(model.output_price_per_million),
                context_window=model.context_window,
                enabled=model.enabled,
                version=model.version,
            )
        await audit.record(
            tenant_id=str(context.tenant_id),
            actor_id=str(context.user_id),
            action="model.configure",
            resource_type="language_model",
            resource_id=response.id,
            outcome="succeeded",
            correlation_id=response.id,
            details={"key": response.key, "min_tier": response.min_tier_code},
        )
        return response

    @router.post("/image-models", response_model=AdminImageModelResponse)
    async def configure_image_model(
        body: AdminImageModelRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AdminImageModelResponse:
        context = await admin_action(access_token, csrf_token)
        defaults = dict(body.default_parameters)
        if body.protocol == "grsai_image2":
            defaults.setdefault("aspectRatio", "1024x1024")
            defaults.setdefault("replyType", "json")
        async with database.session() as session:
            provider = await session.get(ProviderModel, body.provider_id)
            tier = (
                await session.scalars(select(TierModel).where(TierModel.code == body.min_tier_code))
            ).one_or_none()
            if provider is None or tier is None:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY, "provider or tier unavailable"
                )
            model = (
                await session.scalars(
                    select(ImageModelModel).where(ImageModelModel.key == body.key)
                )
            ).one_or_none()
            if model is None:
                model = ImageModelModel(
                    key=body.key,
                    display_name=body.display_name.strip(),
                    provider_id=provider.id,
                    min_tier_id=tier.id,
                )
                session.add(model)
            else:
                model.version += 1
            model.display_name = body.display_name.strip()
            model.provider_id = provider.id
            model.protocol = body.protocol
            model.endpoint_path = body.endpoint_path
            model.min_tier_id = tier.id
            model.price_per_image = body.price_per_image
            model.default_parameters = defaults
            model.enabled = body.enabled
            await session.flush()
            response = AdminImageModelResponse(
                id=model.id,
                key=model.key,
                display_name=model.display_name,
                provider_id=provider.id,
                provider_name=provider.name,
                provider_status=provider.status,
                protocol=model.protocol,
                endpoint_path=model.endpoint_path,
                min_tier_code=tier.code,
                min_tier_name=tier.name,
                price_per_image=float(model.price_per_image),
                default_parameters=dict(model.default_parameters),
                enabled=model.enabled,
                version=model.version,
            )
        await audit.record(
            tenant_id=str(context.tenant_id),
            actor_id=str(context.user_id),
            action="model.configure",
            resource_type="image_model",
            resource_id=response.id,
            outcome="succeeded",
            correlation_id=response.id,
            details={"key": response.key, "protocol": response.protocol},
        )
        return response

    @router.put("/tiers/{tier_code}", response_model=AdminTierResponse)
    async def configure_tier(
        tier_code: str,
        body: AdminTierUpdateRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AdminTierResponse:
        context = await admin_action(access_token, csrf_token)
        async with database.session() as session:
            tier = (
                await session.scalars(select(TierModel).where(TierModel.code == tier_code))
            ).one_or_none()
            if tier is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "tier not found")
            tier.name = body.name.strip()
            tier.rank = body.rank
            tier.monthly_price = body.monthly_price
            tier.monthly_token_quota = body.monthly_token_quota
            tier.enabled = body.enabled
            tier.version += 1
            response = AdminTierResponse(
                code=tier.code,
                name=tier.name,
                rank=tier.rank,
                monthly_price=float(tier.monthly_price),
                monthly_token_quota=tier.monthly_token_quota,
                enabled=tier.enabled,
                version=tier.version,
            )
        await audit.record(
            tenant_id=str(context.tenant_id),
            actor_id=str(context.user_id),
            action="tier.configure",
            resource_type="tier",
            resource_id=tier_code,
            outcome="succeeded",
            correlation_id=tier_code,
            details={"version": tier.version, "enabled": body.enabled},
        )
        return response

    @router.get("/capabilities", response_model=AdminCapabilitiesResponse)
    async def capabilities(
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> AdminCapabilitiesResponse:
        await admin_context(access_token)
        async with database.session() as session:
            templates = list(
                (
                    await session.scalars(
                        select(AgentTemplateVersionModel).order_by(
                            AgentTemplateVersionModel.role_key,
                            AgentTemplateVersionModel.version.desc(),
                        )
                    )
                ).all()
            )
            groups = list(
                (await session.scalars(select(ToolGroupModel).order_by(ToolGroupModel.name))).all()
            )
            tiers_by_id = {
                item.id: item for item in (await session.scalars(select(TierModel))).all()
            }
            mounts = list(
                (
                    await session.scalars(
                        select(AgentToolMountModel).order_by(AgentToolMountModel.role_key)
                    )
                ).all()
            )
            skill_plan_rows = (
                await session.execute(
                    select(RuntimeConfigSnapshotModel, ProjectRunModel, ProjectModel)
                    .join(ProjectRunModel, ProjectRunModel.id == RuntimeConfigSnapshotModel.run_id)
                    .join(ProjectModel, ProjectModel.id == ProjectRunModel.project_id)
                    .order_by(RuntimeConfigSnapshotModel.created_at.desc())
                    .limit(10)
                )
            ).all()
        return AdminCapabilitiesResponse(
            templates=[
                AdminAgentTemplateResponse(
                    id=item.id,
                    role_key=item.role_key,
                    version=item.version,
                    soul=item.soul,
                    default_model_id=item.default_model_id,
                    fallback_model_id=item.fallback_model_id,
                    tool_keys=list(item.tool_keys),
                    policy=dict(item.policy),
                    published=item.published,
                )
                for item in templates
            ],
            tool_groups=[
                {
                    "id": item.id,
                    "key": item.key,
                    "name": item.name,
                    "tool_keys": list(item.tool_keys),
                    "min_tier_code": tiers_by_id[item.min_tier_id].code,
                    "enabled": item.enabled,
                    "version": item.version,
                }
                for item in groups
            ],
            mounts=[
                {
                    "id": item.id,
                    "role_key": item.role_key,
                    "tool_group_id": item.tool_group_id,
                    "enabled": item.enabled,
                }
                for item in mounts
            ],
            skill_plans=[
                {
                    "run_id": snapshot.run_id,
                    "project_id": project.id,
                    "project_name": project.name,
                    "created_at": snapshot.created_at.isoformat(),
                    "plan": {
                        **plan,
                        "creative_profile": dict(snapshot.snapshot).get("creative_profile", {}),
                    },
                }
                for snapshot, _, project in skill_plan_rows
                if isinstance((plan := dict(snapshot.snapshot).get("skill_plan")), dict)
            ],
        )

    @router.post("/agent-templates", response_model=AdminAgentTemplateResponse)
    async def create_template_draft(
        body: AdminAgentTemplateRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AdminAgentTemplateResponse:
        context = await admin_action(access_token, csrf_token)
        async with database.session() as session:
            if await session.get(LanguageModelModel, body.default_model_id) is None:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY, "default model unavailable"
                )
            latest = int(
                await session.scalar(
                    select(func.coalesce(func.max(AgentTemplateVersionModel.version), 0)).where(
                        AgentTemplateVersionModel.role_key == body.role_key
                    )
                )
                or 0
            )
            item = AgentTemplateVersionModel(
                role_key=body.role_key,
                version=latest + 1,
                soul=body.soul.strip(),
                default_model_id=body.default_model_id,
                fallback_model_id=body.fallback_model_id,
                tool_keys=body.tool_keys,
                policy=body.policy,
                published=False,
            )
            session.add(item)
            await session.flush()
            response = AdminAgentTemplateResponse(
                id=item.id,
                role_key=item.role_key,
                version=item.version,
                soul=item.soul,
                default_model_id=item.default_model_id,
                fallback_model_id=item.fallback_model_id,
                tool_keys=list(item.tool_keys),
                policy=dict(item.policy),
                published=False,
            )
        await audit.record(
            tenant_id=str(context.tenant_id),
            actor_id=str(context.user_id),
            action="agent_template.draft.create",
            resource_type="agent_template",
            resource_id=response.id,
            outcome="succeeded",
            correlation_id=response.id,
            details={"role_key": response.role_key, "version": response.version},
        )
        return response

    @router.post(
        "/agent-templates/{template_id}/publish", response_model=AdminAgentTemplateResponse
    )
    async def publish_template(
        template_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AdminAgentTemplateResponse:
        context = await admin_action(access_token, csrf_token)
        async with database.session() as session:
            item = await session.get(AgentTemplateVersionModel, template_id)
            if item is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "template not found")
            item.published = True
            response = AdminAgentTemplateResponse(
                id=item.id,
                role_key=item.role_key,
                version=item.version,
                soul=item.soul,
                default_model_id=item.default_model_id,
                fallback_model_id=item.fallback_model_id,
                tool_keys=list(item.tool_keys),
                policy=dict(item.policy),
                published=True,
            )
        await audit.record(
            tenant_id=str(context.tenant_id),
            actor_id=str(context.user_id),
            action="agent_template.publish",
            resource_type="agent_template",
            resource_id=response.id,
            outcome="succeeded",
            correlation_id=response.id,
            details={"role_key": response.role_key, "version": response.version},
        )
        return response

    @router.post("/tool-groups")
    async def configure_tool_group(
        body: AdminToolGroupRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        context = await admin_action(access_token, csrf_token)
        async with database.session() as session:
            tier = (
                await session.scalars(select(TierModel).where(TierModel.code == body.min_tier_code))
            ).one_or_none()
            if tier is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "tier unavailable")
            item = (
                await session.scalars(select(ToolGroupModel).where(ToolGroupModel.key == body.key))
            ).one_or_none()
            if item is None:
                item = ToolGroupModel(
                    key=body.key,
                    name=body.name.strip(),
                    tool_keys=body.tool_keys,
                    min_tier_id=tier.id,
                    enabled=body.enabled,
                )
                session.add(item)
            else:
                item.name = body.name.strip()
                item.tool_keys = body.tool_keys
                item.min_tier_id = tier.id
                item.enabled = body.enabled
                item.version += 1
            await session.flush()
            response = {
                "id": item.id,
                "key": item.key,
                "version": item.version,
                "enabled": item.enabled,
            }
        await audit.record(
            tenant_id=str(context.tenant_id),
            actor_id=str(context.user_id),
            action="tool_group.configure",
            resource_type="tool_group",
            resource_id=str(response["id"]),
            outcome="succeeded",
            correlation_id=str(response["id"]),
            details={"key": body.key, "enabled": body.enabled},
        )
        return response

    @router.put("/tool-mounts")
    async def configure_tool_mount(
        body: AdminToolMountRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        context = await admin_action(access_token, csrf_token)
        async with database.session() as session:
            if await session.get(ToolGroupModel, body.tool_group_id) is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "tool group not found")
            item = (
                await session.scalars(
                    select(AgentToolMountModel).where(
                        AgentToolMountModel.role_key == body.role_key,
                        AgentToolMountModel.tool_group_id == body.tool_group_id,
                    )
                )
            ).one_or_none()
            if item is None:
                item = AgentToolMountModel(
                    role_key=body.role_key, tool_group_id=body.tool_group_id, enabled=body.enabled
                )
                session.add(item)
            else:
                item.enabled = body.enabled
            await session.flush()
            response = {
                "id": item.id,
                "role_key": item.role_key,
                "tool_group_id": item.tool_group_id,
                "enabled": item.enabled,
            }
        await audit.record(
            tenant_id=str(context.tenant_id),
            actor_id=str(context.user_id),
            action="tool_mount.configure",
            resource_type="agent_tool_mount",
            resource_id=str(response["id"]),
            outcome="succeeded",
            correlation_id=str(response["id"]),
            details={"role_key": body.role_key, "enabled": body.enabled},
        )
        return response

    @router.get("/mcp-governance")
    async def mcp_governance(
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> dict[str, object]:
        await admin_context(access_token)
        async with database.session() as session:
            servers = list(
                (await session.scalars(select(McpServerModel).order_by(McpServerModel.name))).all()
            )
            tiers_by_id = {
                item.id: item.code for item in (await session.scalars(select(TierModel))).all()
            }
            tools = list(
                (await session.scalars(select(McpToolModel).order_by(McpToolModel.name))).all()
            )
            policies = list(
                (
                    await session.scalars(
                        select(SandboxPolicyModel).order_by(SandboxPolicyModel.key)
                    )
                ).all()
            )
        return {
            "servers": [
                {
                    "id": item.id,
                    "key": item.key,
                    "name": item.name,
                    "transport": item.transport,
                    "public_config": dict(item.public_config),
                    "min_tier_code": tiers_by_id[item.min_tier_id],
                    "status": item.status,
                    "latency_ms": item.latency_ms,
                    "enabled": item.enabled,
                    "confirmation_required": item.confirmation_required,
                    "last_error": item.last_error,
                }
                for item in servers
            ],
            "tools": [
                {
                    "id": item.id,
                    "server_id": item.server_id,
                    "key": item.key,
                    "name": item.name,
                    "description": item.description,
                    "whitelisted": item.whitelisted,
                    "enabled": item.enabled,
                }
                for item in tools
            ],
            "policies": [
                {"key": item.key, "mode": item.mode, "version": item.version} for item in policies
            ],
        }

    @router.post("/mcp-servers")
    async def configure_mcp_server(
        body: AdminMcpServerRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, str]:
        context = await admin_action(access_token, csrf_token)
        try:
            server_id = await mcp.configure(
                key=body.key,
                name=body.name.strip(),
                transport=body.transport,
                config=body.config,
                min_tier_code=body.min_tier_code,
                enabled=body.enabled,
                confirmation_required=body.confirmation_required,
            )
        except McpGovernanceError as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
        await audit.record(
            tenant_id=str(context.tenant_id),
            actor_id=str(context.user_id),
            action="mcp_server.configure",
            resource_type="mcp_server",
            resource_id=server_id,
            outcome="succeeded",
            correlation_id=server_id,
            details={"key": body.key, "transport": body.transport},
        )
        return {"id": server_id}

    @router.post("/mcp-servers/{server_id}/discover")
    async def discover_mcp_server(
        server_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        context = await admin_action(access_token, csrf_token)
        try:
            tools = await mcp.discover(server_id)
        except McpGovernanceError as error:
            await audit.record(
                tenant_id=str(context.tenant_id),
                actor_id=str(context.user_id),
                action="mcp_server.discover",
                resource_type="mcp_server",
                resource_id=server_id,
                outcome="failed",
                correlation_id=server_id,
                details={"reason": str(error)},
            )
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
        await audit.record(
            tenant_id=str(context.tenant_id),
            actor_id=str(context.user_id),
            action="mcp_server.discover",
            resource_type="mcp_server",
            resource_id=server_id,
            outcome="succeeded",
            correlation_id=server_id,
            details={"tool_count": len(tools)},
        )
        return {
            "tools": [
                {"key": item.key, "name": item.name, "description": item.description}
                for item in tools
            ]
        }

    @router.put("/mcp-tools/{tool_id}/whitelist", status_code=status.HTTP_204_NO_CONTENT)
    async def whitelist_mcp_tool(
        tool_id: str,
        body: AdminMcpWhitelistRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> None:
        context = await admin_action(access_token, csrf_token)
        async with database.session() as session:
            tool = await session.get(McpToolModel, tool_id)
            if tool is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "MCP tool not found")
            tool.whitelisted = body.whitelisted
        await audit.record(
            tenant_id=str(context.tenant_id),
            actor_id=str(context.user_id),
            action="mcp_tool.whitelist",
            resource_type="mcp_tool",
            resource_id=tool_id,
            outcome="succeeded",
            correlation_id=tool_id,
            details={"whitelisted": body.whitelisted},
        )

    @router.put("/sandbox-policies/{policy_key}")
    async def configure_sandbox(
        policy_key: str,
        body: AdminSandboxRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        context = await admin_action(access_token, csrf_token)
        async with database.session() as session:
            item = await session.get(SandboxPolicyModel, policy_key)
            if item is None:
                item = SandboxPolicyModel(key=policy_key, mode=body.mode)
                session.add(item)
            else:
                item.mode = body.mode
                item.version += 1
            await session.flush()
            response = {"key": item.key, "mode": item.mode, "version": item.version}
        await audit.record(
            tenant_id=str(context.tenant_id),
            actor_id=str(context.user_id),
            action="sandbox_policy.configure",
            resource_type="sandbox_policy",
            resource_id=policy_key,
            outcome="succeeded",
            correlation_id=policy_key,
            details={"mode": body.mode, "version": response["version"]},
        )
        return response

    @router.get("/memories")
    async def list_memories(
        tenant_id: str | None = None,
        project_id: str | None = None,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> dict[str, object]:
        await admin_context(access_token)
        async with database.session() as session:
            query = (
                select(MemoryEntryModel, TenantModel, ProjectModel)
                .join(TenantModel, TenantModel.id == MemoryEntryModel.tenant_id)
                .join(ProjectModel, ProjectModel.id == MemoryEntryModel.project_id)
            )
            if tenant_id:
                query = query.where(MemoryEntryModel.tenant_id == tenant_id)
            if project_id:
                query = query.where(MemoryEntryModel.project_id == project_id)
            rows = (
                await session.execute(query.order_by(MemoryEntryModel.updated_at.desc()).limit(200))
            ).all()
            policies = list(
                (
                    await session.scalars(
                        select(MemoryPolicyModel).order_by(MemoryPolicyModel.role_key)
                    )
                ).all()
            )
            audit_rows = list(
                (
                    await session.scalars(
                        select(MemoryAuditModel)
                        .order_by(MemoryAuditModel.created_at.desc())
                        .limit(200)
                    )
                ).all()
            )
        items = []
        for entry, tenant, project in rows:
            try:
                content = await memories.read(
                    tenant_id=entry.tenant_id, project_id=entry.project_id, entry_id=entry.id
                )
            except (MemoryError, OSError):
                content = ""
            items.append(
                {
                    "id": entry.id,
                    "tenant_id": entry.tenant_id,
                    "tenant_name": tenant.name,
                    "project_id": entry.project_id,
                    "project_name": project.name,
                    "role_key": entry.role_key,
                    "content": content,
                    "content_hash": entry.content_hash,
                    "updated_at": entry.updated_at.isoformat(),
                }
            )
        return {
            "items": items,
            "policies": [
                {
                    "role_key": item.role_key,
                    "memory_max_tokens": item.memory_max_tokens,
                    "trigger_ratio": float(item.trigger_ratio),
                    "reserve_ratio": float(item.reserve_ratio),
                    "memory_instructions": item.memory_instructions,
                    "preserve_creative_decisions": True,
                    "version": item.version,
                }
                for item in policies
            ],
            "audit": [
                {
                    "id": item.id,
                    "tenant_id": item.tenant_id,
                    "project_id": item.project_id,
                    "memory_entry_id": item.memory_entry_id,
                    "actor_id": item.actor_id,
                    "operation": item.operation,
                    "before_hash": item.before_hash,
                    "after_hash": item.after_hash,
                    "created_at": item.created_at.isoformat(),
                }
                for item in audit_rows
            ],
        }

    @router.put("/memories/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def correct_memory(
        entry_id: str,
        tenant_id: str,
        project_id: str,
        body: AdminMemoryContentRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> None:
        context = await admin_action(access_token, csrf_token)
        try:
            await memories.correct(
                tenant_id=tenant_id,
                project_id=project_id,
                entry_id=entry_id,
                actor_id=str(context.user_id),
                content=body.content,
            )
        except MemoryError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error

    @router.post("/memories/{entry_id}/compress", status_code=status.HTTP_204_NO_CONTENT)
    async def compress_memory(
        entry_id: str,
        tenant_id: str,
        project_id: str,
        body: AdminMemoryContentRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> None:
        context = await admin_action(access_token, csrf_token)
        try:
            await memories.replace(
                tenant_id=tenant_id,
                project_id=project_id,
                entry_id=entry_id,
                actor_id=str(context.user_id),
                content=body.content,
                operation="compress",
            )
        except MemoryError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error

    @router.delete("/memories/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_memory(
        entry_id: str,
        tenant_id: str,
        project_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> None:
        context = await admin_action(access_token, csrf_token)
        try:
            await memories.delete(
                tenant_id=tenant_id,
                project_id=project_id,
                entry_id=entry_id,
                actor_id=str(context.user_id),
            )
        except MemoryError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error

    @router.put("/memory-policies/{role_key}")
    async def configure_memory_policy(
        role_key: str,
        body: AdminMemoryPolicyRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        context = await admin_action(access_token, csrf_token)
        if not body.preserve_creative_decisions:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "creative decisions must be preserved"
            )
        if body.trigger_ratio + body.reserve_ratio > 1:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "trigger and reserve ratios exceed context"
            )
        async with database.session() as session:
            item = await session.get(MemoryPolicyModel, role_key)
            if item is None:
                item = MemoryPolicyModel(
                    role_key=role_key,
                    memory_max_tokens=body.memory_max_tokens,
                    trigger_ratio=body.trigger_ratio,
                    reserve_ratio=body.reserve_ratio,
                    memory_instructions=body.memory_instructions,
                    preserve_creative_decisions=True,
                )
                session.add(item)
            else:
                item.memory_max_tokens = body.memory_max_tokens
                item.trigger_ratio = body.trigger_ratio
                item.reserve_ratio = body.reserve_ratio
                item.memory_instructions = body.memory_instructions
                item.preserve_creative_decisions = True
                item.version += 1
            await session.flush()
            response = {
                "role_key": item.role_key,
                "version": item.version,
                "preserve_creative_decisions": True,
            }
        await audit.record(
            tenant_id=str(context.tenant_id),
            actor_id=str(context.user_id),
            action="memory_policy.configure",
            resource_type="memory_policy",
            resource_id=role_key,
            outcome="succeeded",
            correlation_id=role_key,
            details={"version": response["version"]},
        )
        return response

    @router.get("/usage/runs", response_model=AdminUsagePageResponse)
    async def usage_runs(
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> AdminUsagePageResponse:
        await admin_context(access_token)
        async with database.session() as session:
            input_total, output_total, cost_total = (
                await session.execute(
                    select(
                        func.coalesce(func.sum(TokenUsageModel.input_tokens), 0),
                        func.coalesce(func.sum(TokenUsageModel.output_tokens), 0),
                        func.coalesce(func.sum(TokenUsageModel.cost_estimate), 0),
                    )
                )
            ).one()
            grouped = (
                select(
                    TokenUsageModel.run_id.label("run_id"),
                    func.max(TokenUsageModel.trace_id).label("trace_id"),
                    TenantModel.name.label("tenant_name"),
                    ProjectModel.name.label("project_name"),
                    ProjectRunModel.status.label("status"),
                    func.max(TokenUsageModel.agent_role).label("agent_role"),
                    func.max(TokenUsageModel.model_key).label("model_key"),
                    func.sum(TokenUsageModel.input_tokens).label("input_tokens"),
                    func.sum(TokenUsageModel.output_tokens).label("output_tokens"),
                    func.max(
                        UsageReservationModel.monthly_reserved
                        + UsageReservationModel.credits_reserved
                    ).label("reserved_tokens"),
                    func.sum(TokenUsageModel.cost_estimate).label("estimated_cost"),
                    func.max(TokenUsageModel.currency).label("currency"),
                    func.max(TokenUsageModel.input_price_per_million).label(
                        "input_price_per_million"
                    ),
                    func.max(TokenUsageModel.output_price_per_million).label(
                        "output_price_per_million"
                    ),
                    func.max(TokenUsageModel.created_at).label("created_at"),
                )
                .join(ProjectRunModel, ProjectRunModel.id == TokenUsageModel.run_id)
                .join(
                    UsageReservationModel,
                    UsageReservationModel.id == TokenUsageModel.reservation_id,
                )
                .join(ProjectModel, ProjectModel.id == TokenUsageModel.project_id)
                .join(TenantModel, TenantModel.id == TokenUsageModel.tenant_id)
                .group_by(
                    TokenUsageModel.run_id,
                    TenantModel.name,
                    ProjectModel.name,
                    ProjectRunModel.status,
                )
            )
            total = int(
                await session.scalar(select(func.count()).select_from(grouped.subquery())) or 0
            )
            rows = (
                await session.execute(
                    grouped.order_by(func.max(TokenUsageModel.created_at).desc())
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
        items = []
        for row in rows:
            studio = settings.agent_studio_url.rstrip("/") if settings.agent_studio_url else None
            actual_tokens = int(row.input_tokens) + int(row.output_tokens)
            reserved_tokens = int(row.reserved_tokens)
            budget_variance_tokens = actual_tokens - reserved_tokens
            budget_status = (
                "unmeasured"
                if reserved_tokens <= 0
                else "soft_exceeded"
                if budget_variance_tokens > 0
                else "within_range"
            )
            items.append(
                AdminUsageRunResponse(
                    run_id=row.run_id,
                    trace_id=row.trace_id,
                    trace_url=f"{studio}/traces/{row.trace_id}" if studio else None,
                    tenant_name=row.tenant_name,
                    project_name=row.project_name,
                    status=row.status,
                    agent_role=row.agent_role,
                    model_key=row.model_key,
                    input_tokens=int(row.input_tokens),
                    output_tokens=int(row.output_tokens),
                    reserved_tokens=reserved_tokens,
                    budget_variance_tokens=budget_variance_tokens,
                    budget_utilization=actual_tokens / reserved_tokens
                    if reserved_tokens > 0
                    else 0,
                    budget_status=budget_status,
                    estimated_cost=float(row.estimated_cost),
                    currency=row.currency,
                    input_price_per_million=float(row.input_price_per_million),
                    output_price_per_million=float(row.output_price_per_million),
                    is_mock=row.model_key.startswith("mock"),
                    created_at=row.created_at.isoformat(),
                )
            )
        return AdminUsagePageResponse(
            summary=AdminUsageSummaryResponse(
                input_tokens=int(input_total),
                output_tokens=int(output_total),
                total_tokens=int(input_total) + int(output_total),
                estimated_cost=float(cost_total),
                currency="CNY",
            ),
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )

    @router.post(
        "/tenants",
        response_model=AdminTenantResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_tenant(
        body: AdminCreateTenantRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AdminTenantResponse:
        context = await admin_action(access_token, csrf_token)
        normalized_email = body.owner_email.strip().casefold()
        normalized_name = body.name.strip()
        async with database.session() as session:
            if await session.scalar(
                select(UserModel.id).where(UserModel.email == normalized_email)
            ):
                raise HTTPException(status.HTTP_409_CONFLICT, "owner email already exists")
            tier = (
                await session.scalars(
                    select(TierModel).where(
                        TierModel.code == body.tier, TierModel.enabled.is_(True)
                    )
                )
            ).one_or_none()
            if tier is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "tier is unavailable")
            tenant = TenantModel(name=normalized_name, tier=tier.code)
            session.add(tenant)
            await session.flush()
            session.add(
                UserModel(
                    tenant_id=tenant.id,
                    email=normalized_email,
                    password_hash=auth.passwords.hash(body.temporary_password),
                )
            )
            session.add(
                TokenAccountModel(
                    tenant_id=tenant.id,
                    tier=tier.code,
                    period_key=datetime.now(UTC).strftime("%Y-%m"),
                    monthly_available=tier.monthly_token_quota,
                    credits_available=0,
                )
            )
            await session.flush()
            response = AdminTenantResponse(
                id=tenant.id,
                name=tenant.name,
                owner_email=normalized_email,
                tier=tier.code,
                tier_name=tier.name,
                status=tenant.status,
                monthly_used=0,
                monthly_quota=tier.monthly_token_quota,
                credits_available=0,
                created_at=tenant.created_at.isoformat(),
            )
        await audit.record(
            tenant_id=response.id,
            actor_id=str(context.user_id),
            action="tenant.create",
            resource_type="tenant",
            resource_id=response.id,
            outcome="succeeded",
            correlation_id=response.id,
            details={"owner_email": normalized_email, "tier": response.tier},
        )
        return response

    @router.patch("/tenants/{tenant_id}/tier", response_model=AdminTenantResponse)
    async def change_tenant_tier(
        tenant_id: str,
        body: AdminTierChangeRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AdminTenantResponse:
        context = await admin_action(access_token, csrf_token)
        async with database.session() as session:
            tenant = await session.get(TenantModel, tenant_id)
            tier = (
                await session.scalars(
                    select(TierModel).where(
                        TierModel.code == body.tier, TierModel.enabled.is_(True)
                    )
                )
            ).one_or_none()
            if tenant is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")
            if tier is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "tier is unavailable")
            before = tenant.tier
            tenant.tier = tier.code
            account = (
                await session.scalars(
                    select(TokenAccountModel).where(
                        TokenAccountModel.tenant_id == tenant_id,
                        TokenAccountModel.tier == tier.code,
                    )
                )
            ).one_or_none()
            if account is None:
                account = TokenAccountModel(
                    tenant_id=tenant_id,
                    tier=tier.code,
                    period_key=datetime.now(UTC).strftime("%Y-%m"),
                    monthly_available=tier.monthly_token_quota,
                    credits_available=0,
                )
                session.add(account)
            owner_email = (
                await session.scalar(
                    select(UserModel.email)
                    .where(UserModel.tenant_id == tenant_id)
                    .order_by(UserModel.created_at)
                )
            ) or "—"
            await session.flush()
            response = AdminTenantResponse(
                id=tenant.id,
                name=tenant.name,
                owner_email=owner_email,
                tier=tier.code,
                tier_name=tier.name,
                status=tenant.status,
                monthly_used=max(0, tier.monthly_token_quota - account.monthly_available),
                monthly_quota=tier.monthly_token_quota,
                credits_available=account.credits_available,
                created_at=tenant.created_at.isoformat(),
            )
        await audit.record(
            tenant_id=tenant_id,
            actor_id=str(context.user_id),
            action="tenant.tier.change",
            resource_type="tenant",
            resource_id=tenant_id,
            outcome="succeeded",
            correlation_id=tenant_id,
            details={"before": before, "after": body.tier, "note": body.note.strip()},
        )
        return response

    @router.post("/tenants/{tenant_id}/grants", response_model=AdminGrantResponse)
    async def grant_credits(
        tenant_id: str,
        body: AdminGrantRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AdminGrantResponse:
        context = await admin_action(access_token, csrf_token)
        reference = f"grant:{tenant_id}:{body.idempotency_key}"
        async with database.session() as session:
            tenant = await session.get(TenantModel, tenant_id)
            account = (
                await session.scalars(
                    select(TokenAccountModel).where(
                        TokenAccountModel.tenant_id == tenant_id,
                        TokenAccountModel.tier == body.tier,
                    )
                )
            ).one_or_none()
            if tenant is None or account is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant account not found")
            existing = (
                await session.scalars(
                    select(CreditLedgerModel).where(CreditLedgerModel.reference_key == reference)
                )
            ).one_or_none()
            if existing is not None:
                order_id = existing.run_id.removeprefix("admin-grant:")
                order = await session.get(OrderModel, order_id)
                if (
                    order is None
                    or order.tenant_id != tenant_id
                    or order.tier != body.tier
                    or order.token_amount != body.tokens
                ):
                    raise HTTPException(
                        status.HTTP_409_CONFLICT, "idempotency key payload mismatch"
                    )
                return AdminGrantResponse(
                    order_id=order_id,
                    tenant_id=tenant_id,
                    tier=body.tier,
                    granted_tokens=body.tokens,
                    credits_available=account.credits_available,
                    idempotent=True,
                )
            before = account.credits_available
            order = OrderModel(
                tenant_id=tenant_id,
                kind="grant",
                status="succeeded",
                tier=body.tier,
                token_amount=body.tokens,
                note=body.note.strip(),
                actor_id=str(context.user_id),
            )
            session.add(order)
            await session.flush()
            account.credits_available += body.tokens
            session.add(
                CreditLedgerModel(
                    tenant_id=tenant_id,
                    reservation_id=None,
                    reference_key=reference,
                    run_id=f"admin-grant:{order.id}",
                    operation="grant",
                    tier=body.tier,
                    period_key=account.period_key,
                    currency=account.currency,
                    monthly_delta=0,
                    credits_delta=body.tokens,
                    monthly_before=account.monthly_available,
                    monthly_after=account.monthly_available,
                    credits_before=before,
                    credits_after=account.credits_available,
                )
            )
            response = AdminGrantResponse(
                order_id=order.id,
                tenant_id=tenant_id,
                tier=body.tier,
                granted_tokens=body.tokens,
                credits_available=account.credits_available,
                idempotent=False,
            )
        await audit.record(
            tenant_id=tenant_id,
            actor_id=str(context.user_id),
            action="tenant.credits.grant",
            resource_type="order",
            resource_id=response.order_id,
            outcome="succeeded",
            correlation_id=response.order_id,
            details={"tier": body.tier, "tokens": body.tokens, "note": body.note.strip()},
        )
        return response

    @router.patch("/tenants/{tenant_id}/status", status_code=status.HTTP_204_NO_CONTENT)
    async def change_tenant_status(
        tenant_id: str,
        body: AdminStatusRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> None:
        context = await admin_action(access_token, csrf_token)
        if tenant_id == str(context.tenant_id) and body.status == TenantStatus.SUSPENDED:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "cannot suspend the active admin tenant"
            )
        async with database.session() as session:
            tenant = await session.get(TenantModel, tenant_id)
            if tenant is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")
            before = tenant.status
            tenant.status = body.status
        await audit.record(
            tenant_id=tenant_id,
            actor_id=str(context.user_id),
            action="tenant.status.change",
            resource_type="tenant",
            resource_id=tenant_id,
            outcome="succeeded",
            correlation_id=tenant_id,
            details={"before": before, "after": body.status},
        )

    return router
