import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal

from agentscope.agent import Agent, ReActConfig
from agentscope.credential import OpenAICredential
from agentscope.event import (
    AgentEvent,
    CustomEvent,
    TextBlockDeltaEvent,
    ThinkingBlockDeltaEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
    ToolResultEndEvent,
)
from agentscope.mcp import HttpMCPConfig, MCPClient, StdioMCPConfig
from agentscope.message import Msg, TextBlock
from agentscope.model import OpenAIChatModel
from agentscope.tool import Toolkit
from pydantic import SecretStr
from sqlalchemy import select

from scriptnow.platform.agent_factory import AgentFactory, RuntimeConfigError
from scriptnow.platform.config import Settings
from scriptnow.platform.database import Database
from scriptnow.platform.model_supply import (
    CredentialCipher,
    CredentialError,
    ModelSupplyService,
)
from scriptnow.platform.models import (
    AgentStateModel,
    AgentTemplateVersionModel,
    LanguageModelModel,
    McpServerModel,
    McpToolModel,
    ProjectModel,
    ProjectRunModel,
    ProviderModel,
    ProviderStatus,
    TenantAgentConfigModel,
)
from scriptnow.platform.models import (
    RunStatus as RunStatusEnum,
)


class AgentRuntimeError(RuntimeError):
    pass


class AgentRuntimeTimeoutError(AgentRuntimeError):
    """The configured wall-clock limit expired before AgentScope completed."""


class AgentRuntimeIncompleteError(AgentRuntimeError):
    """AgentScope stopped before producing a final user-facing answer."""


AGENT_MAX_ITERATIONS_MESSAGE = (
    "Executed maximum iterations of reasoning-acting loop without finishing the task."
)


def is_incomplete_agent_text(text: str) -> bool:
    normalized = text.strip().casefold()
    return not normalized or AGENT_MAX_ITERATIONS_MESSAGE.casefold() in normalized


def require_completed_agent_text(text: str) -> str:
    if is_incomplete_agent_text(text):
        raise AgentRuntimeIncompleteError(
            "review agent reached its execution limit before completing the review"
        )
    return text.strip()


RuntimeEventSink = Callable[[AgentEvent], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class AgentRuntimeResult:
    text: str
    runtime: str
    model_key: str
    input_tokens: int
    output_tokens: int
    input_price_per_million: Decimal
    output_price_per_million: Decimal
    config_fingerprint: str = ""
    completed: bool = True
    stop_reason: str | None = None
    evidence_manifest: tuple[dict[str, object], ...] = ()
    agent_state: dict[str, object] | None = None


class AgentRuntime:
    """Build and invoke the real AgentScope runtime from a frozen run snapshot."""

    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings
        self.factory = AgentFactory(database)
        self.supply = ModelSupplyService(
            database,
            CredentialCipher(lambda version: settings.credential_master_key),
            key_version=settings.credential_key_version,
        )
        self.cipher = CredentialCipher(lambda version: settings.credential_master_key)

    async def status(self, *, tenant_id: str, project_id: str) -> dict[str, object]:
        roles: dict[str, dict[str, object]] = {}
        async with self.database.session() as session:
            project = await session.get(ProjectModel, project_id)
            if project is None or project.tenant_id != tenant_id:
                raise AgentRuntimeError("project does not exist")
            for role in ("director", "architect", "writer", "reviewer"):
                template = (
                    await session.scalars(
                        select(AgentTemplateVersionModel)
                        .where(
                            AgentTemplateVersionModel.role_key == role,
                            AgentTemplateVersionModel.published.is_(True),
                        )
                        .order_by(AgentTemplateVersionModel.version.desc())
                    )
                ).first()
                override = (
                    await session.scalars(
                        select(TenantAgentConfigModel).where(
                            TenantAgentConfigModel.tenant_id == tenant_id,
                            TenantAgentConfigModel.project_id == project_id,
                            TenantAgentConfigModel.role_key == role,
                        )
                    )
                ).one_or_none()
                model_id = (
                    override.model_id
                    if override
                    else template.default_model_id
                    if template
                    else None
                )
                model = await session.get(LanguageModelModel, model_id) if model_id else None
                provider = await session.get(ProviderModel, model.provider_id) if model else None
                credential_ready = bool(
                    provider
                    and provider.credential_ciphertext
                    and provider.credential_nonce
                    and provider.credential_key_version
                )
                connected = bool(
                    template
                    and model
                    and model.enabled
                    and provider
                    and provider.key != "mock"
                    and provider.status == ProviderStatus.CONNECTED
                    and credential_ready
                )
                roles[role] = {
                    "connected": connected,
                    "model_key": model.key if model else None,
                    "provider_key": provider.key if provider else None,
                    "reason": "connected" if connected else self._reason(template, model, provider),
                }
            # Query active runs for progress visibility
            active_runs = list(
                await session.scalars(
                    select(ProjectRunModel).where(
                        ProjectRunModel.tenant_id == tenant_id,
                        ProjectRunModel.project_id == project_id,
                        ProjectRunModel.status.in_([
                            RunStatusEnum.QUEUED, RunStatusEnum.RUNNING
                        ]),
                    ).order_by(ProjectRunModel.created_at)
                )
            )
            active = [
                {
                    "run_id": run.id,
                    "status": str(run.status),
                    "created_at": run.created_at.isoformat() if run.created_at else None,
                }
                for run in active_runs
            ]
        return {
            "connected": all(item["connected"] for item in roles.values()),
            "roles": roles,
            "active_runs": active,
        }

    async def generate(
        self,
        *,
        tenant_id: str,
        run_id: str,
        role: str,
        content: str,
        context_snapshot: dict[str, object],
        event_sink: RuntimeEventSink | None = None,
        stage_override: str | None = None,
        explicit_skill_keys: tuple[str, ...] = (),
        skills_enabled: bool = True,
    ) -> AgentRuntimeResult:
        try:
            return await asyncio.wait_for(
                self._generate(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    role=role,
                    content=content,
                    context_snapshot=context_snapshot,
                    event_sink=event_sink,
                    stage_override=stage_override,
                    explicit_skill_keys=explicit_skill_keys,
                    skills_enabled=skills_enabled,
                ),
                timeout=self.settings.agent_runtime_timeout_seconds,
            )
        except TimeoutError as error:
            raise AgentRuntimeTimeoutError(
                f"Agent runtime exceeded {self.settings.agent_runtime_timeout_seconds:g} seconds"
            ) from error

    async def inspire(
        self,
        *,
        tenant_id: str,
        medium: str,
        seed: str,
        language: str,
        genres: tuple[str, ...] = (),
    ) -> AgentRuntimeResult:
        """Expand one creative seed before a project exists, using the admitted skill catalog."""
        try:
            snapshot = await self.factory.preview_for_tenant(
                tenant_id=tenant_id,
                role_key="director",
                medium=medium,
                direction={"language": language, "genres": list(genres)},
                stage="ideation",
            )
        except RuntimeConfigError as error:
            raise AgentRuntimeError(str(error)) from error
        values = snapshot.values
        if values.get("provider_key") == "mock":
            raise AgentRuntimeError("real model is not configured for this role")
        provider_id = str(values["provider_id"])
        try:
            credential = await self.supply.get_credential_for_runtime(provider_id)
        except CredentialError as error:
            raise AgentRuntimeError(str(error)) from error
        async with self.database.session() as session:
            provider = await session.get(ProviderModel, provider_id)
            model_record = await session.get(LanguageModelModel, str(values["model_id"]))
        if provider is None or model_record is None or not provider.base_url:
            raise AgentRuntimeError("provider runtime endpoint is incomplete")
        model = self._openai_model(
            credential=OpenAICredential(
                api_key=SecretStr(credential),
                base_url=provider.base_url,
            ),
            model_key=model_record.key,
            stream=False,
            thinking=False,
            context_size=model_record.context_window,
        )
        loaders = self.factory.skill_catalog.loaders_for_plan(
            domain=medium,
            skill_keys=list(values.get("skill_keys") or []),
        )
        agent = Agent(
            name="inspiration-director",
            system_prompt=self._system_prompt(
                "director",
                str(values.get("soul") or ""),
                language=language,
                skill_instructions=self._skill_instructions(values),
            ),
            model=model,
            toolkit=Toolkit(skills_or_loaders=loaders),
            react_config=ReActConfig(
                max_iters=min(
                    self.settings.agent_runtime_default_max_iters,
                    self.settings.agent_runtime_hard_max_iters,
                )
            ),
        )
        prompt = (
            "你正在协助作者把一句灵感扩展成创建项目前的候选设定。"
            "必须遵循系统提示【创作手法与风格指令】中按题材选定的技能要求；"
            "必要时可调用技能工具读取完整说明。不要替作者做最终决定。\n"
            "只返回一个 JSON 对象，不要 Markdown，不要代码围栏。字段必须为："
            "title、premise、tone、world_setting、genre_suggestions、questions。"
            "genre_suggestions 和 questions 是字符串数组；其余字段是字符串。"
            "设定要具体、彼此一致、保留可塑性，questions 最多 3 个。\n\n"
            f"作品形态：{medium}\n创作语言：{language}\n"
            f"作者已选类型：{json.dumps(genres, ensure_ascii=False)}\n"
            f"一句话灵感：{seed}"
        )
        try:
            reply = await asyncio.wait_for(
                agent.reply(Msg(name="creator", role="user", content=[TextBlock(text=prompt)])),
                timeout=self.settings.agent_runtime_timeout_seconds,
            )
        except TimeoutError as error:
            raise AgentRuntimeError("inspiration generation timed out") from error
        except Exception as error:
            raise AgentRuntimeError(f"inspiration generation failed: {error}") from error
        usage = reply.usage
        return AgentRuntimeResult(
            text=self._text_content(reply),
            runtime="agentscope",
            model_key=model_record.key,
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
            input_price_per_million=Decimal(str(model_record.input_price_per_million)),
            output_price_per_million=Decimal(str(model_record.output_price_per_million)),
            config_fingerprint=snapshot.fingerprint,
        )

    async def review_source(
        self,
        *,
        tenant_id: str,
        review_domain: str,
        document_kind: str,
        title: str,
        source_text: str,
        request: str,
        language: str = "zh-CN",
        review_focus: str = "overall",
        explicit_skill_keys: tuple[str, ...] = (),
        conversation: tuple[dict[str, str], ...] = (),
        agent_state: dict[str, object] | None = None,
    ) -> AgentRuntimeResult:
        """Review an uploaded work without creating or mutating a creative project."""
        try:
            snapshot = await self.factory.preview_for_tenant(
                tenant_id=tenant_id,
                role_key="reviewer",
                medium=review_domain,
                direction={"language": language},
                stage="review",
            )
        except RuntimeConfigError as error:
            raise AgentRuntimeError(str(error)) from error
        values = snapshot.values
        if values.get("provider_key") == "mock":
            raise AgentRuntimeError("real model is not configured for the reviewer role")
        provider_id = str(values["provider_id"])
        try:
            credential = await self.supply.get_credential_for_runtime(provider_id)
        except CredentialError as error:
            raise AgentRuntimeError(str(error)) from error
        async with self.database.session() as session:
            provider = await session.get(ProviderModel, provider_id)
            model_record = await session.get(LanguageModelModel, str(values["model_id"]))
        if provider is None or model_record is None or not provider.base_url:
            raise AgentRuntimeError("reviewer runtime endpoint is incomplete")
        if values.get("agentscope_class") != "OpenAIChatModel":
            raise AgentRuntimeError("configured AgentScope model class is not supported yet")

        configured_skill_keys = tuple(values.get("skill_keys") or ())
        selected = list(
            explicit_skill_keys
            or self._review_skill_keys(
                domain=review_domain,
                configured_skill_keys=configured_skill_keys,
                review_focus=review_focus,
            )
        )
        try:
            loaders = self.factory.skill_catalog.loaders_for_plan(
                domain=review_domain,
                skill_keys=selected,
            )
        except Exception as error:
            raise AgentRuntimeError(str(error)) from error
        model = self._openai_model(
            credential=OpenAICredential(
                api_key=SecretStr(credential),
                base_url=provider.base_url,
            ),
            model_key=model_record.key,
            stream=False,
            thinking=False,
            context_size=model_record.context_window,
        )
        agent_kwargs = {
            "name": "standalone-reviewer",
            "system_prompt": self._system_prompt(
                "reviewer",
                str(values.get("soul") or ""),
                language=language,
                skill_instructions=self._skill_instructions(values),
            ),
            "model": model,
            "toolkit": Toolkit(skills_or_loaders=loaders),
            "react_config": ReActConfig(
                max_iters=min(
                    self.settings.agent_runtime_default_max_iters,
                    self.settings.agent_runtime_hard_max_iters,
                )
            ),
        }
        agent = Agent(**agent_kwargs)
        if agent_state:
            try:
                agent = Agent(
                    **agent_kwargs,
                    state=agent.state.model_validate(agent_state),
                )
            except Exception as error:
                raise AgentRuntimeError("saved reviewer state is not restorable") from error

        from scriptnow.review.retrieval import build_review_evidence_pack

        source_character_limit = self.settings.context_retrieval_token_limit * 4
        evidence_pack = build_review_evidence_pack(
            source_text=source_text,
            request=request,
            character_budget=source_character_limit,
        )
        prior_turns = "\n".join(
            f"{'用户' if turn.get('actor') == 'user' else '评审 Agent'}："
            f"{turn.get('content', '').strip()}"
            for turn in conversation
            if turn.get("content", "").strip()
        )
        prompt = (
            "评审一份用户独立上传的作品。必须调用已加载的评审 Skill，并以原文证据为依据。"
            "区分事实、推断与建议；指出定位证据；不得把建议写成已经发生的修改；"
            "不得输出隐藏思维链，也不得向用户展示内部 Skill、工具、模型、字段名或技术配置。"
            "原文已经由系统提供，不得要求用户再次粘贴或上传。把当前请求视为同一评审会话的延续："
            "回答追问时必须沿用"
            "此前已经确认的评审范围和证据口径，除非用户明确改变它们。"
            "请用 Markdown 给出清晰、可执行的评审回复。\n\n"
            f"评审领域：{review_domain}\n文档类型：{document_kind}\n标题：{title}\n"
            f"本轮评审轴线：{review_focus}\n"
            + (
                f"此前对话：\n{prior_turns}\n\n"
                if prior_turns and not agent_state
                else ""
            )
            + f"用户本轮要求：{request}\n"
            f"本轮证据说明：已读取 {evidence_pack.covered_characters} 个字符"
            + (
                "，证据来自开篇、中段、结尾及与本轮要求相关的段落。"
                "引用时必须使用证据编号；证据不足时明确提出下一轮检索目标，不得猜测。"
                if not evidence_pack.full_coverage
                else "，已覆盖全文。引用时必须使用证据编号。"
            )
            + "\n\n原文证据：\n"
            + evidence_pack.prompt_text()
        )
        try:
            reply = await asyncio.wait_for(
                agent.reply(Msg(name="creator", role="user", content=[TextBlock(text=prompt)])),
                timeout=self.settings.agent_runtime_timeout_seconds,
            )
        except TimeoutError as error:
            raise AgentRuntimeTimeoutError("standalone review timed out") from error
        except Exception as error:
            if is_incomplete_agent_text(str(error)):
                return AgentRuntimeResult(
                    text="",
                    runtime="agentscope",
                    model_key=model_record.key,
                    input_tokens=0,
                    output_tokens=0,
                    input_price_per_million=Decimal(str(model_record.input_price_per_million)),
                    output_price_per_million=Decimal(str(model_record.output_price_per_million)),
                    config_fingerprint=snapshot.fingerprint,
                    completed=False,
                    stop_reason="max_iterations",
                    evidence_manifest=evidence_pack.manifest(),
                    agent_state=agent.state.model_dump(mode="json"),
                )
            raise AgentRuntimeError(f"standalone review failed: {error}") from error
        usage = reply.usage
        text = self._text_content(reply)
        completed = not is_incomplete_agent_text(text)
        return AgentRuntimeResult(
            text=text.strip(),
            runtime="agentscope",
            model_key=model_record.key,
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
            input_price_per_million=Decimal(str(model_record.input_price_per_million)),
            output_price_per_million=Decimal(str(model_record.output_price_per_million)),
            config_fingerprint=snapshot.fingerprint,
            completed=completed,
            stop_reason=None if completed else "max_iterations",
            evidence_manifest=evidence_pack.manifest(),
            agent_state=agent.state.model_dump(mode="json"),
        )

    def _review_skill_keys(
        self,
        *,
        domain: str,
        configured_skill_keys: tuple[str, ...],
        review_focus: str,
    ) -> tuple[str, ...]:
        """Narrow configured reviewer skills by a stable user-facing review axis."""
        if review_focus == "overall":
            return configured_skill_keys
        focus_terms = {
            "structure": ("structure", "story", "plot", "graph", "continuity", "causality"),
            "character": ("character", "relationship", "emotion", "intimacy", "voice"),
            "pacing": ("pacing", "rhythm", "hook", "retention", "serial"),
            "market": ("market", "platform", "audience", "commercial"),
            "adaptation": ("screen", "adaptation", "production", "acquisition"),
        }.get(review_focus, ())
        if not focus_terms:
            return configured_skill_keys
        descriptors = {
            skill.name: skill
            for skill in self.factory.skill_catalog.for_domain(domain)
        }
        matched = tuple(
            key
            for key in configured_skill_keys
            if key in descriptors
            and any(
                term in f"{descriptors[key].name} {descriptors[key].description}".lower()
                for term in focus_terms
            )
        )
        return matched or configured_skill_keys

    async def _generate(
        self,
        *,
        tenant_id: str,
        run_id: str,
        role: str,
        content: str,
        context_snapshot: dict[str, object],
        event_sink: RuntimeEventSink | None = None,
        stage_override: str | None = None,
        explicit_skill_keys: tuple[str, ...] = (),
        skills_enabled: bool = True,
    ) -> AgentRuntimeResult:
        try:
            snapshot = await self.factory.snapshot_for_run(
                tenant_id=tenant_id,
                run_id=run_id,
                role_key=role,
                stage_override=stage_override,
                explicit_skill_keys=explicit_skill_keys,
                skills_enabled=skills_enabled,
            )
        except RuntimeConfigError as error:
            raise AgentRuntimeError(str(error)) from error
        values = snapshot.values
        if values.get("provider_key") == "mock":
            raise AgentRuntimeError("real model is not configured for this role")
        provider_id = str(values["provider_id"])
        try:
            credential = await self.supply.get_credential_for_runtime(provider_id)
        except CredentialError as error:
            raise AgentRuntimeError(str(error)) from error
        async with self.database.session() as session:
            provider = await session.get(ProviderModel, provider_id)
            model_record = await session.get(LanguageModelModel, str(values["model_id"]))
        if provider is None or model_record is None or not provider.base_url:
            raise AgentRuntimeError("provider runtime endpoint is incomplete")
        if values.get("agentscope_class") != "OpenAIChatModel":
            raise AgentRuntimeError("configured AgentScope model class is not supported yet")

        credential_config = OpenAICredential(
            api_key=SecretStr(credential), base_url=provider.base_url
        )
        # Agent planning uses skills/tools. OpenAI-compatible providers that expose a
        # separate thinking mode commonly reject forced tool selection while thinking
        # is enabled. Keep the tool phase deterministic and observable; user-facing
        # reasoning is emitted as an explicit writing brief instead of leaking hidden
        # model reasoning into the manuscript channel.
        model = self._openai_model(
            credential=credential_config,
            model_key=model_record.key,
            stream=event_sink is not None,
            thinking=False,
            context_size=model_record.context_window,
        )
        skill_domain = str(values.get("skill_domain") or "")
        loaders = []
        if skill_domain in {"novel", "script"}:
            loaders.extend(
                self.factory.skill_catalog.loaders_for_plan(
                    domain=skill_domain,
                    skill_keys=list(values.get("skill_keys") or []),
                )
            )
        mcp_clients = await self._mcp_clients(list(values.get("tool_keys") or []))
        prompt = self._compose_prompt(
            content=content,
            creative_profile=dict(values.get("creative_profile") or {}),
            approved_source_profile=values.get("approved_source_profile"),
            context_snapshot=context_snapshot,
        )
        connected_clients: list[MCPClient] = []
        try:
            for client in mcp_clients:
                if client.is_stateful:
                    await client.connect()
                    connected_clients.append(client)
            agent = Agent(
                name=str(values.get("display_name") or role),
                system_prompt=self._system_prompt(
                    role,
                    str(values.get("soul") or ""),
                    language=str(
                        dict(values.get("creative_profile") or {}).get("language") or "zh-CN"
                    ),
                    skill_instructions=self._skill_instructions(values),
                ),
                model=model,
                toolkit=Toolkit(skills_or_loaders=loaders, mcps=mcp_clients),
                react_config=ReActConfig(
                    max_iters=min(
                        int(
                            dict(values.get("policy") or {}).get(
                                "max_iters",
                                self.settings.agent_runtime_default_max_iters,
                            )
                        ),
                        self.settings.agent_runtime_hard_max_iters,
                    )
                ),
            )
            try:
                if event_sink is None:
                    reply = await agent.reply(
                        Msg(name="creator", role="user", content=[TextBlock(text=prompt)])
                    )
                else:
                    phase_title = (
                        "正在建立评审框架与证据范围"
                        if role == "reviewer"
                        else "正在形成创作策略"
                    )
                    await event_sink(
                        CustomEvent(
                            name="scriptnow.phase",
                            value={
                                "phase": "planning",
                                "state": "start",
                                "title": phase_title,
                            },
                        )
                    )
                    planning_text = await self._run_planning_phase(
                        agent=agent,
                        prompt=prompt,
                        event_sink=event_sink,
                        role=role,
                    )
                    if not planning_text:
                        raise RuntimeError("Agent planning completed without a usable brief.")
                    await event_sink(
                        CustomEvent(
                            name="scriptnow.phase",
                            value={
                                "phase": "planning",
                                "state": "end",
                                "title": (
                                    "评审框架"
                                    if role == "reviewer"
                                    else "创作策略"
                                ),
                                "content": planning_text,
                            },
                        )
                    )
                    delivery_model = self._openai_model(
                        credential=credential_config,
                        model_key=model_record.key,
                        stream=True,
                        thinking=False,
                        context_size=model_record.context_window,
                    )
                    delivery = await delivery_model(
                        [
                            Msg(
                                name="system",
                                role="system",
                                content=[
                                    TextBlock(
                                        text=self._system_prompt(
                                            role,
                                            str(values.get("soul") or ""),
                                            language=str(
                                                dict(values.get("creative_profile") or {}).get(
                                                    "language"
                                                )
                                                or "zh-CN"
                                            ),
                                            skill_instructions=self._skill_instructions(values),
                                        )
                                    )
                                ],
                            ),
                            Msg(
                                name="creator",
                                role="user",
                                content=[
                                    TextBlock(
                                        text=(
                                            f"{prompt}\n\nAgent working brief:\n"
                                            f"{planning_text}\n\n"
                                            + (
                                                "Now deliver a concise, evidence-grounded review response. "
                                                "Separate findings, evidence, impact and recommended next action. "
                                                "Do not claim to have changed the work. Do not mention hidden "
                                                "reasoning or fabricate evidence."
                                                if role == "reviewer"
                                                else (
                                                    "Now deliver the requested creative artifact. Follow the "
                                                    "output contract in the request exactly; do not mention the "
                                                    "brief, tools, or your process."
                                                )
                                            )
                                        )
                                    )
                                ],
                            ),
                        ]
                    )
                    text_buffer = ""
                    final_response = None
                    async for chunk in delivery:  # type: ignore[union-attr]
                        if chunk.is_last:
                            final_response = chunk
                            continue
                        for block in chunk.content:
                            if isinstance(block, TextBlock) and block.text:
                                text_buffer += block.text
                                if len(text_buffer) >= 160:
                                    await event_sink(
                                        TextBlockDeltaEvent(
                                            reply_id=f"{run_id}:delivery",
                                            block_id="manuscript",
                                            delta=text_buffer,
                                            metadata={"phase": "delivery"},
                                        )
                                    )
                                    text_buffer = ""
                    if text_buffer:
                        await event_sink(
                            TextBlockDeltaEvent(
                                reply_id=f"{run_id}:delivery",
                                block_id="manuscript",
                                delta=text_buffer,
                                metadata={"phase": "delivery"},
                            )
                        )
                    if final_response is None:
                        raise RuntimeError("Streaming delivery did not produce a final response.")
                    reply = Msg(
                        name=str(values.get("display_name") or role),
                        role="assistant",
                        content=final_response.content,
                    )
                    reply.usage = final_response.usage
            except Exception as error:
                raise AgentRuntimeError(f"model invocation failed: {error}") from error
        finally:
            for client in reversed(connected_clients):
                if client.is_connected:
                    await client.close()
        usage = reply.usage
        await self._persist_state(
            tenant_id=tenant_id,
            run_id=run_id,
            role=role,
            context_snapshot=context_snapshot,
            context_tokens=usage.input_tokens if usage else max(1, len(prompt) // 4),
            context_limit=model_record.context_window,
        )
        return AgentRuntimeResult(
            text=self._text_content(reply),
            runtime="agentscope",
            model_key=model_record.key,
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
            input_price_per_million=Decimal(str(model_record.input_price_per_million)),
            output_price_per_million=Decimal(str(model_record.output_price_per_million)),
            config_fingerprint=snapshot.fingerprint,
        )

    @staticmethod
    def _text_content(message: Msg) -> str:
        """Read only AgentScope TextBlocks; thinking/tool-only replies have no manuscript."""
        value = message.get_text_content()
        return value.strip() if isinstance(value, str) else ""

    @staticmethod
    def _compose_prompt(
        *,
        content: str,
        creative_profile: dict[str, object],
        approved_source_profile: object,
        context_snapshot: dict[str, object],
    ) -> str:
        """Assemble one auditable context envelope with an explicit precedence contract."""
        return (
            "上下文优先级（发生冲突时必须按此顺序处理）：\n"
            "1. 服务端项目事实快照，包括已采纳事实与最新有效人工修订；\n"
            "2. 用户当前任务中的明确要求；\n"
            "3. 项目创作档案中的世界观规则、语言与创作边界；\n"
            "4. 用户已批准的来源蒸馏画像；\n"
            "5. Skill 与工具给出的策略建议。\n"
            "低优先级内容不得覆盖高优先级事实。未批准的来源候选不得使用。\n\n"
            "用户任务：\n"
            f"{content}\n\n"
            "项目创作档案：\n"
            f"{json.dumps(creative_profile, ensure_ascii=False, sort_keys=True)}\n\n"
            "用户已批准的来源蒸馏画像（仅作创作策略，不是已采纳事实）：\n"
            f"{json.dumps(approved_source_profile or {}, ensure_ascii=False, sort_keys=True)}\n\n"
            "服务端项目事实快照（唯一事实依据；不得虚构已采纳内容）：\n"
            f"{json.dumps(context_snapshot, ensure_ascii=False, sort_keys=True)}"
        )

    @staticmethod
    def _openai_model(
        *,
        credential: OpenAICredential,
        model_key: str,
        stream: bool,
        thinking: bool,
        context_size: int,
    ) -> OpenAIChatModel:
        """Create a phase-scoped model so thinking/tools/prose never share a channel."""
        return OpenAIChatModel(
            credential=credential,
            model=model_key,
            parameters=OpenAIChatModel.Parameters(thinking_enable=thinking),
            stream=stream,
            context_size=context_size,
            # AgentScope maps this to providers that implement the OpenAI-compatible
            # thinking extension. Providers that ignore extension fields still receive
            # the standard parameters above.
            extra_body={"enable_thinking": thinking},
        )

    @staticmethod
    async def _run_planning_phase(
        *,
        agent: Agent,
        prompt: str,
        event_sink: RuntimeEventSink,
        role: str = "writer",
    ) -> str:
        """Run planning through AgentScope's public stream and return visible brief text."""
        visible_text: list[str] = []
        task = (
            "Use the available project skills and tools to prepare an evidence-grounded "
            "review brief for the requested scope. Identify the evaluation frame, inspect "
            "relevant artifacts, and distinguish observations from recommendations. Do not "
            "rewrite the work and do not expose hidden chain-of-thought."
            if role == "reviewer"
            else (
                "Use the available project skills and tools to prepare a compact writing "
                "brief for the requested unit. Resolve continuity, scene movement, character "
                "desire, setup/payoff and source evidence. Explain the decisions in concise, "
                "user-readable terms. Do not write manuscript prose and do not expose hidden "
                "chain-of-thought."
            )
        )
        request = Msg(
            name="creator",
            role="user",
            content=[
                TextBlock(
                    text=(
                        task + "\n\n" + prompt
                    )
                )
            ],
        )
        async for event in agent.reply_stream(request):
            if isinstance(event, TextBlockDeltaEvent):
                if not event.delta:
                    continue
                visible_text.append(event.delta)
                await event_sink(
                    ThinkingBlockDeltaEvent(
                        reply_id=event.reply_id,
                        block_id=event.block_id,
                        delta=event.delta,
                        metadata={**event.metadata, "phase": "planning"},
                    )
                )
            elif isinstance(event, ThinkingBlockDeltaEvent):
                if event.delta:
                    await event_sink(
                        event.model_copy(
                            update={"metadata": {**event.metadata, "phase": "planning"}}
                        )
                    )
            elif isinstance(event, ToolCallStartEvent | ToolCallEndEvent | ToolResultEndEvent):
                await event_sink(
                    event.model_copy(
                        update={"metadata": {**event.metadata, "phase": "planning"}}
                    )
                )
        return "".join(visible_text).strip()

    async def _mcp_clients(self, tool_keys: list[object]) -> list[MCPClient]:
        requested: dict[str, set[str]] = {}
        for value in tool_keys:
            parts = str(value).split(".", 2)
            if len(parts) == 3 and parts[0] == "mcp":
                requested.setdefault(parts[1], set()).add(parts[2])
        if not requested:
            return []
        async with self.database.session() as session:
            rows = (
                await session.execute(
                    select(McpServerModel, McpToolModel)
                    .join(McpToolModel, McpToolModel.server_id == McpServerModel.id)
                    .where(
                        McpServerModel.key.in_(requested),
                        McpServerModel.enabled.is_(True),
                        McpServerModel.status == "connected",
                        McpServerModel.confirmation_required.is_(False),
                        McpToolModel.whitelisted.is_(True),
                        McpToolModel.enabled.is_(True),
                    )
                )
            ).all()
        grouped: dict[str, tuple[McpServerModel, list[str]]] = {}
        for server, tool in rows:
            if tool.key not in requested.get(server.key, set()):
                continue
            grouped.setdefault(server.key, (server, []))[1].append(tool.key)
        clients: list[MCPClient] = []
        for key, (server, tools) in grouped.items():
            config = json.loads(
                self.cipher.decrypt(
                    server.secret_ciphertext,
                    server.secret_nonce,
                    version=server.secret_key_version,
                    context=server.id,
                )
            )
            if server.transport == "http":
                mcp_config = HttpMCPConfig(
                    url=str(config["url"]),
                    headers=config.get("headers"),
                    timeout=float(config.get("timeout", 30)),
                )
                stateful = False
            elif server.transport == "stdio":
                mcp_config = StdioMCPConfig(
                    command=str(config["command"]),
                    args=list(config.get("args", [])),
                    env=config.get("env"),
                    cwd=config.get("cwd"),
                )
                stateful = True
            else:
                continue
            clients.append(
                MCPClient(
                    name=key,
                    is_stateful=stateful,
                    mcp_config=mcp_config,
                    enable_tools=tools,
                )
            )
        return clients

    async def _persist_state(
        self,
        *,
        tenant_id: str,
        run_id: str,
        role: str,
        context_snapshot: dict[str, object],
        context_tokens: int,
        context_limit: int,
    ) -> None:
        async with self.database.session() as session:
            run = await session.get(ProjectRunModel, run_id)
            if run is None or run.tenant_id != tenant_id:
                raise AgentRuntimeError("runtime run does not exist")
            state = (
                await session.scalars(
                    select(AgentStateModel).where(
                        AgentStateModel.tenant_id == tenant_id,
                        AgentStateModel.project_id == run.project_id,
                        AgentStateModel.role_key == role,
                    )
                )
            ).one_or_none()
            if state is None:
                state = AgentStateModel(
                    tenant_id=tenant_id,
                    project_id=run.project_id,
                    role_key=role,
                )
                session.add(state)
            else:
                state.state_version += 1
            state.serialized_state = context_snapshot
            state.context_tokens = max(1, context_tokens)
            state.context_limit = context_limit

    @staticmethod
    def _system_prompt(
        role: str,
        soul: str,
        *,
        language: str = "zh-CN",
        skill_instructions: str = "",
    ) -> str:
        # Development seed v1 used this delivery-oriented placeholder as the
        # writer's identity. Ignore it for existing databases so it cannot
        # flatten creative behavior after richer skills are selected.
        if soul.strip() == "Produce deterministic development output.":
            soul = ""
        responsibility = {
            "director": "负责创意发散与故事核心，不越权改写已采纳事实。",
            "architect": "负责蓝图与 StoryMap，只提出可审查的结构建议。",
            "writer": (
                "负责正文创作与修订，严格服从已采纳蓝图和当前选区；建立作品专属叙述声音，"
                "通过具体感知、潜台词与有代价的选择呈现人物，而不是完成情节说明。"
            ),
            "reviewer": (
                "负责诊断与审读，明确证据、影响和建议，不直接改写正文；优先识别声音趋同、"
                "解释性写作、虚假深刻与没有改变关系风险的情感表达。服务端项目事实快照含有"
                " evidence_manifest.documents 时，直接审读其中稿件；未指定焦点时默认审读已提供的"
                "全部项目稿件，不得要求用户再次粘贴正文。若 coverage 为 partial，只需说明未覆盖单元，"
                "并继续审读已有证据。面向用户只呈现自然语言结论、原文证据、影响与可执行建议；"
                "不得展示内部 Skill、模型、工具、字段名、运行配置或隐藏思维链。"
            ),
        }.get(role, "在授权范围内协助创作。")
        body = (
            f"你是 ScriptNow 的 {role} Agent。{responsibility}\n"
            f"项目创作语言为 {language}。除非用户明确要求翻译，否则所有创意、蓝图、正文与审读输出都必须使用该语言。\n\n"
            f"{soul}"
        )
        if skill_instructions.strip():
            body += (
                "\n\n【创作手法与风格指令】系统根据本项目题材、类型、语言与平台自动选定的技能要求，"
                "必须遵循；与正文交付契约冲突时，交付格式以契约为准，创作手法以本节为准。\n"
                + skill_instructions.strip()
            )
        return body.strip()

    def _skill_instructions(self, values: dict[str, object]) -> str:
        domain = str(values.get("skill_domain") or "")
        keys = values.get("skill_keys")
        if not domain or not keys:
            return ""
        try:
            items = self.factory.skill_catalog.instructions_for(
                domain=domain,
                skill_keys=tuple(keys),
                max_chars=self.settings.skill_prompt_max_chars,
            )
        except Exception:
            return ""
        if not items:
            return ""
        return "\n\n".join(f"### 技能：{name}\n{text}" for name, text in items)

    @staticmethod
    def _reason(template: object, model: object, provider: ProviderModel | None) -> str:
        if template is None:
            return "template_missing"
        if model is None:
            return "model_missing"
        if not getattr(model, "enabled", False):
            return "model_disabled"
        if provider is None or provider.key == "mock":
            return "mock_only"
        if provider.status != ProviderStatus.CONNECTED:
            return "provider_disconnected"
        return "credential_missing"
