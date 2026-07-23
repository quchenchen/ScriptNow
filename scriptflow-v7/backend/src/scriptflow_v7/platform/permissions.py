from dataclasses import dataclass
from enum import StrEnum


class PermissionMode(StrEnum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    DENY = "deny"


class SandboxPolicy(StrEnum):
    DIRECT = "direct"
    SANDBOX = "sandbox"
    SANDBOX_CONFIRM = "sandbox_confirm"


@dataclass(frozen=True, slots=True)
class PermissionDecision:
    mode: PermissionMode
    sandboxed: bool
    reason: str


class PermissionEngine:
    def decide(
        self,
        *,
        tool_key: str,
        mounted_tools: set[str],
        sandbox_policy: SandboxPolicy,
        user_confirmed: bool = False,
    ) -> PermissionDecision:
        if tool_key not in mounted_tools:
            return PermissionDecision(PermissionMode.DENY, False, "tool_not_mounted")
        if tool_key.startswith("domain.read.") or tool_key.startswith("propose_"):
            return PermissionDecision(PermissionMode.ALLOW, False, "trusted_domain_operation")
        if tool_key.startswith("workspace."):
            return PermissionDecision(PermissionMode.ALLOW, True, "project_workspace_only")
        if tool_key.startswith(("bash.", "mcp.")):
            sandboxed = sandbox_policy != SandboxPolicy.DIRECT
            confirmation_required = (
                sandbox_policy == SandboxPolicy.SANDBOX_CONFIRM or tool_key.startswith("mcp.")
            )
            if confirmation_required and not user_confirmed:
                return PermissionDecision(
                    PermissionMode.CONFIRM, sandboxed, "user_confirmation_required"
                )
            return PermissionDecision(PermissionMode.ALLOW, sandboxed, "confirmed_restricted_tool")
        return PermissionDecision(
            PermissionMode.CONFIRM, True, "unknown_tool_requires_confirmation"
        )
