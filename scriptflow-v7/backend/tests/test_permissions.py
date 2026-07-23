from scriptflow_v7.platform.permissions import PermissionEngine, PermissionMode, SandboxPolicy


def test_domain_reads_and_proposals_are_allowed_only_when_mounted() -> None:
    engine = PermissionEngine()
    mounted = {"domain.read.story_map", "propose_patch"}
    assert (
        engine.decide(
            tool_key="domain.read.story_map",
            mounted_tools=mounted,
            sandbox_policy=SandboxPolicy.SANDBOX,
        ).mode
        == PermissionMode.ALLOW
    )
    assert (
        engine.decide(
            tool_key="propose_patch", mounted_tools=mounted, sandbox_policy=SandboxPolicy.SANDBOX
        ).mode
        == PermissionMode.ALLOW
    )
    assert (
        engine.decide(
            tool_key="domain.read.secret",
            mounted_tools=mounted,
            sandbox_policy=SandboxPolicy.SANDBOX,
        ).mode
        == PermissionMode.DENY
    )


def test_workspace_is_sandboxed_and_bash_mcp_require_policy_confirmation() -> None:
    engine = PermissionEngine()
    mounted = {"workspace.read", "bash.execute", "mcp.fetch"}
    workspace = engine.decide(
        tool_key="workspace.read", mounted_tools=mounted, sandbox_policy=SandboxPolicy.DIRECT
    )
    bash = engine.decide(
        tool_key="bash.execute", mounted_tools=mounted, sandbox_policy=SandboxPolicy.SANDBOX_CONFIRM
    )
    mcp = engine.decide(
        tool_key="mcp.fetch", mounted_tools=mounted, sandbox_policy=SandboxPolicy.SANDBOX
    )
    confirmed = engine.decide(
        tool_key="mcp.fetch",
        mounted_tools=mounted,
        sandbox_policy=SandboxPolicy.SANDBOX,
        user_confirmed=True,
    )

    assert workspace.mode == PermissionMode.ALLOW
    assert workspace.sandboxed is True
    assert workspace.reason == "project_workspace_only"
    assert bash.mode == mcp.mode == PermissionMode.CONFIRM
    assert confirmed.mode == PermissionMode.ALLOW
    assert confirmed.sandboxed is True
