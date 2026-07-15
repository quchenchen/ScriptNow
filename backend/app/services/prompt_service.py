"""Prompt Template Service — configurable system prompts stored in DB."""
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func
from sqlalchemy import select
from app.models import Base

DEFAULT_PROMPTS = {
    "ideation": """你是短剧创意孵化专家。基于用户偏好生成3个差异化方案。
格式：严格用 <PLAN id="A/B/C" title="..." genre="..." hook="..."> 包裹每个方案。
类型约束：严格匹配用户指定的类型标签。风格约束：节奏和人设需体现风格偏好。
禁止输出问候语和确认语。""",
    "structure": """你是故事架构专家。基于选中方案，产出完整架构。
## 输出格式
### 核心梗概（一句话+世界观）
### 角色设定（每个角色：姓名·年龄·性别·性格·背景·弧光）
### 分集大纲（10集，每集一句话概要+关键冲突）
### 爽点分布图（每集标注1-3个爽点类型）
使用 tool: query_characters 查看已有角色，plant_foreshadow 埋设伏笔。""",
    "writing": """你是短剧剧本撰写师。严格按格式：\n【场景N】地点·时间\n△动作描述\n角色：对白\n\n规则：\n1. 每集600-1500字\n2. 结尾必须埋钩子\n3. 对话前用△描述动作/表情\n4. 禁止输出JSON/问候语/元对话\n5. 写完后调用 save_episode 保存\n6. 使用 query_characters 确保角色一致\n7. 用 plant_foreshadow 埋设伏笔""",
    "review": "你是剧本质量审核专家。从连贯性、角色一致性、爽点密度、语言质量四个维度评分(1-10)。每集输出评分+改进建议。",
    "polish": "你是剧本润色师。提升文学性和画面感，保持原有情节不变。每句对话都要经得起品味。",
}


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False)
    content = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PromptService:
    """Load and manage prompt templates from DB, with file fallback."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, name: str) -> str:
        r = await self.db.execute(select(PromptTemplate).where(PromptTemplate.name == name))
        tmpl = r.scalar_one_or_none()
        if tmpl:
            return tmpl.content
        # Fallback to default
        return DEFAULT_PROMPTS.get(name, DEFAULT_PROMPTS.get("writing", ""))

    async def seed_defaults(self):
        """Insert default prompts if table is empty."""
        r = await self.db.execute(select(PromptTemplate))
        if r.scalar_one_or_none():
            return  # Already seeded
        for name, content in DEFAULT_PROMPTS.items():
            self.db.add(PromptTemplate(name=name, content=content))
        await self.db.commit()

    async def update(self, name: str, content: str):
        r = await self.db.execute(select(PromptTemplate).where(PromptTemplate.name == name))
        tmpl = r.scalar_one_or_none()
        if tmpl:
            tmpl.content = content
        else:
            self.db.add(PromptTemplate(name=name, content=content))
        await self.db.commit()
