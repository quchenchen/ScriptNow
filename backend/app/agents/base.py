"""
Agent Base — Abstract base class for all Agents.
"""
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from ..core.llm_gateway import get_llm, LLMRequest
from ..core.skill_loader import get_skill_loader
from ..core.state import AgentState

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base for all creation pipeline agents."""

    name: str = "base"
    agent_type: str = "creative"  # creative | analytical | translation
    skills: list[str] = []

    def __init__(self):
        self.llm = get_llm()
        self.skill_loader = get_skill_loader()

    def _build_system_prompt(self) -> str:
        """Build system prompt from skill files."""
        if not self.skills:
            return ""
        return self.skill_loader.load_multi(self.skills)

    async def _llm_json(self, user_prompt: str, temperature: float = 0.7) -> dict:
        """Call LLM with JSON output format."""
        system = self._build_system_prompt()
        req = LLMRequest(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=8192,
            agent_type=self.agent_type,
        )
        result = await self.llm.json_chat(req)
        return result

    async def _llm_text(self, user_prompt: str, temperature: float = 0.8) -> str:
        """Call LLM with text output."""
        system = self._build_system_prompt()
        req = LLMRequest(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=8192,
            agent_type=self.agent_type,
        )
        return await self.llm.chat(req)

    def _log_action(self, state: AgentState, action: str, detail: str = ""):
        """Log agent action to state."""
        log_entry = {
            "agent": self.name,
            "action": action,
            "timestamp": datetime.now().isoformat(),
            "detail": detail,
        }
        if "agent_logs" not in state:
            state["agent_logs"] = []
        state["agent_logs"].append(log_entry)

    @abstractmethod
    async def run(self, state: AgentState) -> AgentState:
        """Execute the agent. Returns updated state."""
        ...
