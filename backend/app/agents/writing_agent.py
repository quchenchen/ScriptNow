"""
Writing Agent — 逐集剧本撰写
负责：将大纲转化为标准短剧格式正文
"""
import json
from .base import BaseAgent
from ..core.state import AgentState


class WritingAgent(BaseAgent):
    name = "writing"
    agent_type = "creative"
    skills = ["writing/main"]

    async def run(self, state: AgentState) -> AgentState:
        structure = state.get("story_structure") or {}
        outlines = structure.get("episodes_outline", [])

        if not outlines:
            state["errors"].append("WritingAgent: 无分集大纲，无法撰写")
            return state

        # Determine which episodes to write
        current_ep = state.get("current_episode", 0)
        # Write all unwritten episodes
        start_ep = current_ep
        total_eps = len(outlines)
        episodes_to_write = min(5, total_eps - start_ep)  # Batch 5 episodes per run

        self._log_action(state, "start",
            f"撰写第 {start_ep+1}-{start_ep+episodes_to_write} 集 (共{total_eps}集)")

        new_episodes = []
        for i in range(start_ep, start_ep + episodes_to_write):
            outline = outlines[i]
            revision_hints = self._get_revision_hints(state, i)

            prompt = self._build_episode_prompt(state, outline, revision_hints)
            episode = await self._llm_json(prompt, temperature=0.85)

            if isinstance(episode, dict):
                episode["episode"] = i + 1
                new_episodes.append(episode)
                self._log_action(state, "episode_done", f"第{i+1}集完成")

        # Merge with existing episodes
        existing = state.get("episodes", [])
        # Replace or append
        for ep in new_episodes:
            ep_num = ep.get("episode", 0)
            existing_idx = next((j for j, e in enumerate(existing)
                                 if e.get("episode") == ep_num), None)
            if existing_idx is not None:
                existing[existing_idx] = ep
            else:
                existing.append(ep)

        state["episodes"] = sorted(existing, key=lambda e: e.get("episode", 0))
        state["writing_version"] = state.get("writing_version", 0) + 1
        state["current_episode"] = start_ep + episodes_to_write
        state["current_stage"] = "writing"

        self._log_action(state, "complete",
            f"完成第 {start_ep+1}-{start_ep+episodes_to_write} 集, "
            f"共 {len(state['episodes'])} 集")
        return state

    def _get_revision_hints(self, state: AgentState, ep_index: int) -> str:
        """Get revision hints from previous review for this episode."""
        reviews = state.get("review_results", [])
        for rev in reviews:
            if rev.get("episode") == ep_index + 1:
                issues = rev.get("issues", [])
                if issues:
                    hints = "\n".join(
                        f"- [{i['severity']}] {i['description']} → {i['suggestion']}"
                        for i in issues
                    )
                    return f"\n## 上次审核问题（请修正）\n{hints}"
        return ""

    def _build_episode_prompt(
        self, state: AgentState, outline: dict, revision_hints: str
    ) -> str:
        structure = state.get("story_structure") or {}
        characters = structure.get("characters", [])

        char_summary = "\n".join(
            f"- {c['name']}（{c['role']}）: {c.get('personality', [])}"
            for c in characters[:6]
        )

        return f"""## 创作任务
撰写短剧第 {outline.get('episode', '?')} 集的完整剧本正文。

## 分集大纲
- 钩子: {outline.get('hook', '')}
- 内容: {outline.get('summary', '')}
- 悬念: {outline.get('cliffhanger', '')}

## 角色信息
{char_summary}

## 前情提要
{self._get_prev_episodes_summary(state)}

{revision_hints}

## 格式要求
使用【场景X】地点 · 时间 格式，△ 开头表示动作，严格遵循 System Prompt 规范。"""
