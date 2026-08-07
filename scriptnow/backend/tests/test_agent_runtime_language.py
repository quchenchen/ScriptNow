import types

import pytest
from agentscope.model import OpenAIChatModel

from scriptnow.platform.agent_runtime import AgentRuntime, AgentRuntimeError


def test_system_prompt_enforces_project_creative_language() -> None:
    prompt = AgentRuntime._system_prompt("writer", "保持人物一致。", language="en-US")

    assert "项目创作语言为 en-US" in prompt


def test_system_prompt_decontaminates_legacy_deterministic_writer_soul() -> None:
    prompt = AgentRuntime._system_prompt(
        "writer", "Produce deterministic development output.", language="en-US"
    )

    assert "deterministic development output" not in prompt
    assert "作品专属叙述声音" in prompt
    assert "所有创意、蓝图、正文与审读输出都必须使用该语言" in prompt


def test_resolve_agentscope_class_supports_known_short_name() -> None:
    assert AgentRuntime._resolve_agentscope_class("OpenAIChatModel") is OpenAIChatModel


def test_resolve_agentscope_class_rejects_invalid_namespace() -> None:
    with pytest.raises(
        AgentRuntimeError,
        match="is not in allowed namespace",
    ):
        AgentRuntime._resolve_agentscope_class("json.decoder.JSONDecoder")


def test_resolve_agentscope_class_supports_model_module_shortcuts(monkeypatch) -> None:
    module = types.ModuleType("agentscope.model")
    module.DummyModel = OpenAIChatModel

    monkeypatch.setattr(
        "scriptnow.platform.agent_runtime.import_module",
        lambda name: {"agentscope.model": module}[name],
    )

    assert (
        AgentRuntime._resolve_agentscope_class("DummyModel")
        is OpenAIChatModel
    )


def test_resolve_agentscope_class_rejects_non_subclass(monkeypatch) -> None:
    module = types.ModuleType("agentscope.model")

    class NotChatModel:
        pass

    module.NotChatModel = NotChatModel

    monkeypatch.setattr(
        "scriptnow.platform.agent_runtime.import_module",
        lambda name: {"agentscope.model": module}[name],
    )

    with pytest.raises(
        AgentRuntimeError,
        match="valid ChatModelBase subclass",
    ):
        AgentRuntime._resolve_agentscope_class("NotChatModel")
