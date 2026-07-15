"""
Structure Agent — 故事架构设计
负责：题材选择、人物设计、分集大纲、爽点分布
"""
import json
from .base import BaseAgent
from ..core.state import AgentState


class StructureAgent(BaseAgent):
    name = "structure"
    agent_type = "creative"
    skills = ["structure/main"]

    async def run(self, state: AgentState) -> AgentState:
        self._log_action(state, "start", f"用户创意: {state.get('user_idea', '')[:50]}...")

        prompt = self._build_user_prompt(state)
        result = await self._llm_json(prompt, temperature=0.8)

        state["story_structure"] = result
        state["structure_version"] = 1
        state["current_stage"] = "structure"
        state["stage_history"].append({
            "stage": "structure",
            "timestamp": state["agent_logs"][-1]["timestamp"] if state["agent_logs"] else "",
            "agent": self.name,
            "status": "completed",
        })

        self._log_action(state, "complete",
            f"生成 {len(result.get('characters', []))} 个角色, "
            f"{len(result.get('episodes_outline', []))} 集大纲")
        return state

    def _build_user_prompt(self, state: AgentState) -> str:
        idea = state.get("user_idea", "")
        audience = state.get("target_audience", "男频")
        genres = state.get("genre_preference", [])
        culture = state.get("cultural_background", "国内")

        parts = [
            f"## 创作任务\n根据以下信息，设计一部短剧的完整故事架构。",
            f"\n## 用户创意\n{idea}",
            f"\n## 创作约束",
            f"- 目标受众: {audience}",
            f"- 文化背景: {culture}",
        ]
        if genres:
            parts.append(f"- 偏好题材: {', '.join(genres)}")

        parts.append(f"\n## 输出要求\n请严格按照 System Prompt 中的 JSON Schema 输出完整的故事架构。确保每个角色有独立动线，爽点分布均匀，集末悬念有力。")
        return "\n".join(parts)
