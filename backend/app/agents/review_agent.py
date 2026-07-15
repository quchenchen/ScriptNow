"""
Review Agent — 多维度质量审核 + Ralph Loop 控制
"""
from .base import BaseAgent
from ..core.state import AgentState
from ..core.config import MAX_RALPH_LOOP_RETRIES, REVIEW_PASS_THRESHOLD, REVIEW_REVISE_THRESHOLD


class ReviewAgent(BaseAgent):
    name = "review"
    agent_type = "analytical"
    skills = ["review/main"]

    async def run(self, state: AgentState) -> AgentState:
        episodes = state.get("episodes", [])
        if not episodes:
            state["errors"].append("ReviewAgent: 无剧本可审核")
            return state

        current_ep = state.get("current_episode", 0)
        # Review only newly written episodes
        review_range = self._get_review_range(state, len(episodes))

        self._log_action(state, "start",
            f"审核第 {review_range[0]}-{review_range[1]} 集")

        # Episode-level review
        for i in range(review_range[0] - 1, review_range[1]):
            ep = episodes[i]
            prompt = self._build_episode_review_prompt(state, ep, i)
            result = await self._llm_json(prompt, temperature=0.3)
            result["episode"] = i + 1
            state["review_results"].append(result)

        # Overall review if all episodes are done
        if review_range[1] >= len(episodes):
            overall = await self._overall_review(state)
            state["overall_review"] = overall

            # Ralph Loop decision
            score = overall.get("overall_score", 0)
            if score >= REVIEW_PASS_THRESHOLD:
                state["current_stage"] = "review_passed"
                self._log_action(state, "pass", f"总评分 {score}, 通过")
            elif state.get("retry_count", 0) >= MAX_RALPH_LOOP_RETRIES:
                state["current_stage"] = "review_max_retries"
                self._log_action(state, "max_retries",
                    f"重试 {state['retry_count']} 次仍未通过，评分 {score}")
            elif score >= REVIEW_REVISE_THRESHOLD:
                state["current_stage"] = "review_revise"
                state["retry_count"] = state.get("retry_count", 0) + 1
                self._log_action(state, "revise",
                    f"评分 {score}, 需修订 (第{state['retry_count']}次)")
            else:
                state["current_stage"] = "review_restructure"
                state["retry_count"] = state.get("retry_count", 0) + 1
                self._log_action(state, "restructure",
                    f"评分 {score}, 需重新架构 (第{state['retry_count']}次)")

        return state

    def _get_review_range(self, state: AgentState, total_eps: int) -> tuple:
        """Determine which episodes to review."""
        reviewed = {r.get("episode", 0) for r in state.get("review_results", [])}
        # Review last 5 unwritten-or-revised episodes
        for i in range(total_eps - 1, -1, -1):
            if (i + 1) not in reviewed:
                start = max(0, i - 4)
                return (start + 1, i + 1)
        return (1, min(5, total_eps))

    def _build_episode_review_prompt(
        self, state: AgentState, episode: dict, ep_index: int
    ) -> str:
        structure = state.get("story_structure", {})
        outline = (structure.get("episodes_outline", []) or [])
        expected = outline[ep_index] if ep_index < len(outline) else {}

        scenes_text = "\n\n".join(
            f"【场景{s['scene_number']}】{s.get('location', '')} · {s.get('time', '')}\n{s.get('content', '')}"
            for s in episode.get("scenes", [])
        )[:3000]  # Truncate for token budget

        return f"""## 审核任务
审核短剧第 {ep_index + 1} 集的剧本质量。

## 大纲对照
- 预期钩子: {expected.get('hook', '')}
- 预期内容: {expected.get('summary', '')}
- 预期悬念: {expected.get('cliffhanger', '')}

## 剧本正文（截取）
{scenes_text}

## 审核要求
按照 System Prompt 中的五维度标准进行审核，输出 JSON 格式的审核结果。"""

    async def _overall_review(self, state: AgentState) -> dict:
        """Generate overall project review."""
        structure = state.get("story_structure", {})
        episodes = state.get("episodes", [])
        ep_reviews = state.get("review_results", [])

        # Summarize episode reviews
        review_summary = "\n".join(
            f"- 第{r['episode']}集: 评分{r.get('overall_score', '?')}, "
            f"问题数{len(r.get('issues', []))}"
            for r in ep_reviews[-10:]  # Last 10 reviews
        )

        prompt = f"""## 整体审核
对整个剧本进行整体性评估。

## 剧本信息
- 标题: {structure.get('title', '')}
- 类型: {structure.get('genre', [])}
- 已写完集数: {len(episodes)}

## 逐集审核摘要
{review_summary}

## 要求
按照 System Prompt 的五维度标准，结合逐集审核结果，给出整体评分和建议。"""
        return await self._llm_json(prompt, temperature=0.3)
