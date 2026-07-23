from scriptflow_v7.platform.agent_runtime import AgentRuntime


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
