"""
Asset + Prompt Agent — 资产提取与 Seedance 提示词生成
参考 Toonflow 项目的资产分析 + Seedance Director Formula 模式
"""
from ..core.state import AgentState
from .base import BaseAgent


class AssetPromptAgent(BaseAgent):
    """
    资产提取 + 视频提示词生成 Agent。
    从完成剧本中提取角色/场景/道具资产，生成 Seedance 2.0 提示词。
    """
    name = "asset_prompt"
    agent_type = "creative"
    skills = ["asset_prompt/main"]

    async def run(self, state: AgentState) -> AgentState:
        episodes = state.get("episodes", [])
        structure = state.get("story_structure", {})

        if not episodes:
            state["errors"].append("AssetPromptAgent: 无剧本可分析")
            return state

        self._log_action(state, "start", f"分析 {len(episodes)} 集剧本")

        # Phase 1: Extract assets
        assets_prompt = self._build_asset_extraction_prompt(state)
        assets_result = await self._llm_json(assets_prompt, temperature=0.4)

        state["character_assets"] = assets_result.get("character_assets", [])
        state["location_assets"] = assets_result.get("location_assets", [])
        state["prop_assets"] = assets_result.get("prop_assets", [])
        state["continuity_ledger"] = assets_result.get("continuity_ledger", [])

        char_count = len(state["character_assets"])
        loc_count = len(state["location_assets"])
        prop_count = len(state["prop_assets"])
        self._log_action(state, "assets_done",
            f"提取 {char_count} 角色, {loc_count} 场景, {prop_count} 道具")

        # Phase 2: Generate Seedance prompts for key scenes
        key_scenes = self._extract_key_scenes(state)
        prompt_parts = []
        for scene in key_scenes[:5]:  # Limit to 5 scenes for token budget
            sp = self._build_shot_prompt_prompt(state, scene)
            prompt_parts.append(sp)

        # Generate prompts in batches of 3
        all_prompts = []
        for i in range(0, len(prompt_parts), 3):
            batch = "\n\n---\n\n".join(prompt_parts[i:i+3])
            batch_prompt = f"## 批量生成视频提示词\n为以下场景生成 Seedance 2.0 视频提示词（每个场景独立输出）:\n\n{batch}"
            result = await self._llm_json(batch_prompt, temperature=0.6)
            if isinstance(result, list):
                all_prompts.extend(result)
            elif isinstance(result, dict):
                items = result.get("shot_prompts", [result])
                all_prompts.extend(items)

        state["shot_prompts"] = all_prompts
        state["current_stage"] = "asset_prompt"

        self._log_action(state, "prompts_done",
            f"生成 {len(all_prompts)} 个分镜提示词")
        return state

    def _extract_key_scenes(self, state: AgentState) -> list[dict]:
        """Extract key scenes from episodes for prompt generation."""
        scenes = []
        for ep in state.get("episodes", []):
            for sc in ep.get("scenes", []):
                # Only include scenes with significant visual content
                content = sc.get("content", "")
                if len(content) > 100 and self._has_visual_elements(content):
                    scenes.append({
                        "episode": ep.get("episode", 0),
                        "scene_number": sc.get("scene_number", 0),
                        "location": sc.get("location", ""),
                        "time": sc.get("time", ""),
                        "content": content[:500],
                        "hook_elements": sc.get("hook_elements", []),
                    })
        return scenes

    def _has_visual_elements(self, content: str) -> bool:
        """Check if scene content has meaningful visual elements."""
        visual_keywords = ["△", "场景", "镜头", "画面", "灯光", "背景", "服装"]
        return any(kw in content for kw in visual_keywords)

    def _build_asset_extraction_prompt(self, state: AgentState) -> str:
        structure = state.get("story_structure", {})
        episodes = state.get("episodes", [])

        # Summarize episodes
        ep_summaries = []
        for ep in episodes[:10]:  # First 10 episodes
            scenes_summary = "; ".join(
                f"场景{s['scene_number']}:{s.get('location','')}"
                for s in ep.get("scenes", [])[:3]
            )
            ep_summaries.append(f"第{ep.get('episode','?')}集: {scenes_summary}")

        characters = structure.get("characters", [])
        char_names = [c["name"] for c in characters]

        return f"""## 资产提取任务
从以下短剧剧本中提取所有制作资产。

## 剧本信息
- 标题: {structure.get('title', '')}
- 角色: {', '.join(char_names)}

## 剧集摘要
{chr(10).join(ep_summaries)}

## 要求
按照 System Prompt 的规范，提取角色资产、场景资产、道具资产和连续性台账。"""

    def _build_shot_prompt_prompt(self, state: AgentState, scene: dict) -> str:
        return f"""## 场景 {scene['episode']}-{scene['scene_number']}
地点: {scene['location']}
时间: {scene['time']}
内容: {scene['content']}

为该场景生成 1-2 个 Seedance 2.0 视频分镜提示词，使用 Director Formula: [主体]+[动作]+[镜头]+[光线]+[风格]。"""

    def _get_prev_episodes_summary(self, state: AgentState) -> str:
        """Get brief summary of previous episodes for context."""
        episodes = state.get("episodes", [])
        if len(episodes) <= 1:
            return "（第一集，无前情）"

        prev = episodes[-2] if len(episodes) >= 2 else None
        if not prev:
            return "（无前情）"

        cliffhanger = prev.get("cliffhanger", "")
        return f"上一集结尾: {cliffhanger}"
