import hashlib
import json
from dataclasses import dataclass

from sqlalchemy import select

from scriptnow.platform.config import Settings, get_settings
from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    AgentTemplateVersionModel,
    AgentToolMountModel,
    DistillationDecision,
    LanguageModelModel,
    McpServerModel,
    McpToolModel,
    MemoryPolicyModel,
    ProjectModel,
    ProjectRunModel,
    ProviderModel,
    ProviderStatus,
    RuntimeConfigSnapshotModel,
    SandboxPolicyModel,
    SourceProfileModel,
    TenantAgentConfigModel,
    TenantModel,
    TierModel,
    ToolGroupModel,
)
from scriptnow.platform.skills import (
    CreativeProfile,
    SkillCatalog,
    SkillResolver,
    resolve_skills_root,
)


class RuntimeConfigError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    snapshot_id: str
    fingerprint: str
    values: dict[str, object]


class AgentFactory:
    def __init__(
        self,
        database: Database,
        skill_catalog: SkillCatalog | None = None,
        *,
        settings: Settings | None = None,
    ) -> None:
        self.database = database
        self.skill_catalog = skill_catalog or SkillCatalog(resolve_skills_root())
        self.settings = settings or get_settings()

    async def snapshot_for_run(
        self,
        *,
        tenant_id: str,
        run_id: str,
        role_key: str,
        selected_model_id: str | None = None,
        stage_override: str | None = None,
        explicit_skill_keys: tuple[str, ...] = (),
        skills_enabled: bool = True,
    ) -> RuntimeConfig:
        async with self.database.session() as session:
            existing = (
                await session.scalars(
                    select(RuntimeConfigSnapshotModel).where(
                        RuntimeConfigSnapshotModel.run_id == run_id
                    )
                )
            ).one_or_none()
            if existing is not None:
                return RuntimeConfig(existing.id, existing.fingerprint, dict(existing.snapshot))

            tenant = await session.get(TenantModel, tenant_id)
            run = await session.get(ProjectRunModel, run_id)
            if tenant is None or (run is not None and run.tenant_id != tenant_id):
                raise RuntimeConfigError("tenant does not exist")
            tenant_tier = (
                await session.scalars(select(TierModel).where(TierModel.code == tenant.tier))
            ).one_or_none()
            template = (
                await session.scalars(
                    select(AgentTemplateVersionModel)
                    .where(
                        AgentTemplateVersionModel.role_key == role_key,
                        AgentTemplateVersionModel.published.is_(True),
                    )
                    .order_by(AgentTemplateVersionModel.version.desc())
                )
            ).first()
            if tenant_tier is None or template is None:
                raise RuntimeConfigError("runtime configuration is incomplete")
            override = None
            if run is not None:
                override = (
                    await session.scalars(
                        select(TenantAgentConfigModel).where(
                            TenantAgentConfigModel.tenant_id == tenant_id,
                            TenantAgentConfigModel.project_id == run.project_id,
                            TenantAgentConfigModel.role_key == role_key,
                        )
                    )
                ).one_or_none()
            model_id = (
                selected_model_id
                or (override.model_id if override else None)
                or template.default_model_id
            )
            model = await session.get(LanguageModelModel, model_id)
            if model is None:
                raise RuntimeConfigError("model does not exist")
            provider = await session.get(ProviderModel, model.provider_id)
            minimum = await session.get(TierModel, model.min_tier_id)
            if (
                not model.enabled
                or provider is None
                or provider.status != ProviderStatus.CONNECTED
                or minimum is None
                or tenant_tier.rank < minimum.rank
            ):
                raise RuntimeConfigError("model is not available for tenant")

            mounted_rows = (
                await session.execute(
                    select(AgentToolMountModel, ToolGroupModel, TierModel)
                    .join(ToolGroupModel, ToolGroupModel.id == AgentToolMountModel.tool_group_id)
                    .join(TierModel, TierModel.id == ToolGroupModel.min_tier_id)
                    .where(
                        AgentToolMountModel.role_key == role_key,
                        AgentToolMountModel.enabled.is_(True),
                        ToolGroupModel.enabled.is_(True),
                    )
                )
            ).all()
            mounted_tool_keys = list(template.tool_keys)
            tool_group_versions: dict[str, int] = {}
            for _, group, group_tier in mounted_rows:
                if tenant_tier.rank >= group_tier.rank:
                    mounted_tool_keys.extend(group.tool_keys)
                    tool_group_versions[group.key] = group.version
            mcp_rows = (
                await session.execute(
                    select(McpToolModel, McpServerModel, TierModel)
                    .join(McpServerModel, McpServerModel.id == McpToolModel.server_id)
                    .join(TierModel, TierModel.id == McpServerModel.min_tier_id)
                    .where(
                        McpToolModel.whitelisted.is_(True),
                        McpToolModel.enabled.is_(True),
                        McpServerModel.enabled.is_(True),
                        McpServerModel.status == "connected",
                    )
                )
            ).all()
            allowed_mcp = {
                f"mcp.{server.key}.{tool.key}"
                for tool, server, mcp_tier in mcp_rows
                if tenant_tier.rank >= mcp_tier.rank
            }
            mounted_tool_keys = [
                key for key in mounted_tool_keys if not key.startswith("mcp.") or key in allowed_mcp
            ]
            sandbox = await session.get(SandboxPolicyModel, "default")
            memory_policy = await session.get(MemoryPolicyModel, role_key)
            project = await session.get(ProjectModel, run.project_id) if run is not None else None
            approved_source_profile = await self._approved_source_profile(
                session, tenant_id, project
            )
            skill_domain = str(project.medium) if project is not None else None
            creative_profile = (
                CreativeProfile.from_direction(
                    medium=skill_domain, direction=dict(project.direction)
                )
                if project is not None and skill_domain in {"novel", "script"}
                else None
            )
            stage = stage_override or {
                "director": "ideation",
                "architect": "planning",
                "writer": "writing",
                "reviewer": "review",
            }.get(role_key, "execution")
            skill_plan = (
                SkillResolver(
                    self.skill_catalog,
                    optional_limit=self.settings.skill_plan_optional_limit,
                ).resolve(
                    profile=creative_profile,
                    role_key=role_key,
                    stage=stage,
                    explicit_skill_keys=explicit_skill_keys,
                )
                if creative_profile is not None and skills_enabled
                else None
            )
            selected_skills = (
                tuple(selection.skill for selection in skill_plan.selections) if skill_plan else ()
            )

            values: dict[str, object] = {
                "role_key": template.role_key,
                "template_version": template.version,
                "template_version_id": template.id,
                "display_name": override.custom_name
                if override and override.custom_name
                else role_key,
                "soul": "\n\n".join(
                    value
                    for value in [template.soul, override.soul_override if override else None]
                    if value
                ),
                "tenant_agent_config_id": override.id if override else None,
                "model_id": model.id,
                "model_key": model.key,
                "model_version": model.version,
                "provider_id": provider.id,
                "provider_key": provider.key,
                "agentscope_class": model.agentscope_class,
                "fallback_model_id": template.fallback_model_id,
                "tool_keys": list(dict.fromkeys(mounted_tool_keys)),
                "tool_group_versions": tool_group_versions,
                "skill_domain": skill_domain,
                "skill_keys": [item.name for item in selected_skills],
                "skill_digests": {item.name: item.digest for item in selected_skills},
                "skill_catalog_fingerprint": self.skill_catalog.fingerprint(
                    domain=skill_domain, role_key=role_key
                )
                if skill_domain in {"novel", "script"}
                else None,
                "creative_profile": creative_profile.as_dict() if creative_profile else None,
                "approved_source_profile": self._profile_snapshot(approved_source_profile),
                "skill_plan": skill_plan.as_dict() if skill_plan else None,
                "policy": dict(template.policy),
                "sandbox_policy": sandbox.mode if sandbox else "sandbox_confirm",
                "memory_policy": {
                    "memory_max_tokens": memory_policy.memory_max_tokens,
                    "trigger_ratio": float(memory_policy.trigger_ratio),
                    "reserve_ratio": float(memory_policy.reserve_ratio),
                    "memory_instructions": memory_policy.memory_instructions,
                    "preserve_creative_decisions": True,
                    "version": memory_policy.version,
                }
                if memory_policy
                else None,
                "tier_code": tenant_tier.code,
                "tier_version": tenant_tier.version,
                "pricing": {
                    "input_per_million": str(model.input_price_per_million),
                    "output_per_million": str(model.output_price_per_million),
                },
            }
            canonical = json.dumps(
                values, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            record = RuntimeConfigSnapshotModel(
                run_id=run_id,
                tenant_id=tenant.id,
                template_version_id=template.id,
                snapshot=values,
                fingerprint=fingerprint,
            )
            session.add(record)
            await session.flush()
            return RuntimeConfig(record.id, fingerprint, dict(values))

    async def preview_for_tenant(
        self,
        *,
        tenant_id: str,
        role_key: str,
        medium: str,
        direction: dict[str, object],
        stage: str,
    ) -> RuntimeConfig:
        """Resolve an auditable, non-persistent config for pre-project creative assistance."""
        if medium not in {"novel", "script"}:
            raise RuntimeConfigError("creative preview only supports novel or script")
        async with self.database.session() as session:
            tenant = await session.get(TenantModel, tenant_id)
            if tenant is None:
                raise RuntimeConfigError("tenant does not exist")
            tenant_tier = (
                await session.scalars(select(TierModel).where(TierModel.code == tenant.tier))
            ).one_or_none()
            template = (
                await session.scalars(
                    select(AgentTemplateVersionModel)
                    .where(
                        AgentTemplateVersionModel.role_key == role_key,
                        AgentTemplateVersionModel.published.is_(True),
                    )
                    .order_by(AgentTemplateVersionModel.version.desc())
                )
            ).first()
            if tenant_tier is None or template is None:
                raise RuntimeConfigError("runtime configuration is incomplete")
            model = await session.get(LanguageModelModel, template.default_model_id)
            provider = await session.get(ProviderModel, model.provider_id) if model else None
            minimum = await session.get(TierModel, model.min_tier_id) if model else None
            if (
                model is None
                or not model.enabled
                or provider is None
                or provider.status != ProviderStatus.CONNECTED
                or minimum is None
                or tenant_tier.rank < minimum.rank
            ):
                raise RuntimeConfigError("model is not available for tenant")
            profile = CreativeProfile.from_direction(medium=medium, direction=direction)
            plan = SkillResolver(
                self.skill_catalog,
                optional_limit=self.settings.skill_plan_optional_limit,
            ).resolve(
                profile=profile,
                role_key=role_key,
                stage=stage,
            )
            selected_skills = tuple(selection.skill for selection in plan.selections)
            values: dict[str, object] = {
                "role_key": role_key,
                "display_name": role_key,
                "soul": template.soul,
                "model_id": model.id,
                "model_key": model.key,
                "model_version": model.version,
                "provider_id": provider.id,
                "provider_key": provider.key,
                "agentscope_class": model.agentscope_class,
                "skill_domain": medium,
                "skill_keys": [item.name for item in selected_skills],
                "skill_digests": {item.name: item.digest for item in selected_skills},
                "creative_profile": profile.as_dict(),
                "skill_plan": plan.as_dict(),
                "pricing": {
                    "input_per_million": str(model.input_price_per_million),
                    "output_per_million": str(model.output_price_per_million),
                },
            }
            canonical = json.dumps(
                values, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            return RuntimeConfig("preview", fingerprint, values)

    @staticmethod
    async def _approved_source_profile(session, tenant_id: str, project: ProjectModel | None):
        if project is None:
            return None
        query = (
            select(SourceProfileModel)
            .where(
                SourceProfileModel.project_id == project.id,
                SourceProfileModel.tenant_id == tenant_id,
                SourceProfileModel.decision == DistillationDecision.APPROVED,
            )
            .order_by(SourceProfileModel.version.desc())
        )
        return (await session.scalars(query)).first()

    @staticmethod
    def _profile_snapshot(profile: SourceProfileModel | None) -> dict[str, object] | None:
        if profile is None:
            return None
        return {
            "id": profile.id,
            "version": profile.version,
            "profile": profile.profile,
            "evidence_ids": profile.evidence_ids,
            "conflicts": profile.conflicts,
            "exclusions": profile.exclusions,
        }
