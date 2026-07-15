"""Context Engine — Long-term memory with upgraded foreshadow & character models."""
import json, re
import aiosqlite
from app.db import DB_PATH


async def build_context(project_id: int, stage: str, episode_num: int = 0) -> str:
    """Build rich context for agent generation, including characters + foreshadows."""
    parts = []

    # ── Characters ──
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM characters WHERE project_id = ? AND status != 'deceased' ORDER BY role",
            (project_id,))
        chars = [dict(c) for c in await cur.fetchall()]
        if chars:
            lines = ["## 角色表"]
            for c in chars:
                org_flag = "🏛 " if c.get("is_organization") else ""
                line = f"- **{c['name']}**({c.get('role','supporting')})"
                if c.get("age"): line += f" {c['age']}岁"
                if c.get("gender"): line += f" {c['gender']}"
                if c.get("traits"): line += f" | 特质:{c['traits']}"
                if c.get("personality"): line += f" | 性格:{c['personality'][:60]}"
                if c.get("current_state"): line += f" | 现状:{c['current_state'][:40]}"
                if c.get("arc"): line += f" | 弧光:{c['arc'][:60]}"
                if c.get("first_appearance"): line += f" | 初登场:{c['first_appearance']}集"
                lines.append(line)
            parts.append("\n".join(lines))

    # ── Foreshadows ──
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Open foreshadows that need attention
        cur = await db.execute(
            """SELECT * FROM foreshadows WHERE project_id = ? AND status IN ('pending','planted')
               ORDER BY importance DESC, urgency DESC LIMIT 10""",
            (project_id,))
        fores = [dict(f) for f in await cur.fetchall()]
        if fores:
            lines = ["\n## 待回收伏笔"]
            for f in fores:
                status_emoji = {'pending':'⏳','planted':'🌱','partially_resolved':'🔄'}.get(f['status'],'❓')
                line = f"- {status_emoji} **{f['title']}** [{f.get('category','mystery')}]"
                if f.get('plant_episode'): line += f" | EP{f['plant_episode']}埋"
                if f.get('target_episode'): line += f" → EP{f['target_episode']}回收"
                if f.get('importance',0) > 0.7: line += " | ⚠高重要"
                line += f" | {f['description'][:100]}"
                if f.get('import_category'):
                    try:
                        tags = json.loads(f['import_category'])
                        line += f" | 关联角色:{','.join(tags[:3])}"
                    except: pass
                lines.append(line)
            parts.append("\n".join(lines))

    # ── Previous episodes ──
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT episode_number, title, scenes FROM episodes WHERE project_id = ? AND status = 'done' ORDER BY episode_number DESC LIMIT 2",
            (project_id,))
        eps = [dict(e) for e in await cur.fetchall()]
        if eps:
            lines = ["\n## 前情提要"]
            for e in reversed(eps):
                sc = json.loads(e.get('scenes','[]'))
                content = sc[0].get('content','')[:200] if sc else ''
                lines.append(f"**EP{e['episode_number']}** {e.get('title','')}\n{content}")
            parts.append("\n".join(lines))

    return "\n\n".join(parts)


async def save_episode_context(project_id: int, episode_num: int, content: str):
    """Parse generated episode for characters, foreshadows, and assets to track."""

    # ── Extract new characters ──
    char_pattern = re.compile(r'(?:^|\n)\s*(?:△.*?\n)?\s*([\u4e00-\u9fff]{2,3})[：:]')
    found_names = set()
    blacklist = {'然而','但是','因为','所以','如果','可以','已经','可是','不过','还是','这个','那个','什么','怎么','非常','一定','可能','必须','应该','需要','能够','没有','不要','不会','知道','觉得','认为','发现','突然','立刻','马上','刚才','现在','然后','终于','难道','原来','原来','居然','其实','反正','虽然','但是','而且','或者','并且'}
    for m in char_pattern.finditer(content):
        name = m.group(1)
        if name not in blacklist:
            found_names.add(name)

    async with aiosqlite.connect(DB_PATH) as db:
        for name in found_names:
            cur = await db.execute("SELECT id FROM characters WHERE project_id = ? AND name = ?", (project_id, name))
            if not await cur.fetchone():
                try:
                    await db.execute(
                        "INSERT INTO characters (project_id, name, role, first_appearance, last_appearance) VALUES (?,?,?,?,?)",
                        (project_id, name, 'supporting', episode_num, episode_num))
                except: pass
            else:
                await db.execute("UPDATE characters SET last_appearance = ? WHERE project_id = ? AND name = ?",
                                 (episode_num, project_id, name))
        await db.commit()

    # ── Extract new foreshadows ──
    # Match: 钩子：... 悬疑：... 伏笔：... or standalone cliffhanger lines
    hook_pattern = re.compile(r'(?:钩子|悬疑|伏笔|埋|彩蛋|预告)[：:]\s*(.+?)(?:\n|$)', re.MULTILINE)
    # Also match last 1-2 lines of episode as potential hooks
    lines = content.strip().split('\n')
    last_lines = [l.strip() for l in lines[-3:] if l.strip() and not l.strip().startswith('△')]
    hooks_found = set()
    for m in hook_pattern.finditer(content):
        hooks_found.add(m.group(1).strip()[:100])
    # Add last non-dialogue line as potential hook if short
    if last_lines and len(last_lines[-1]) < 60 and '：' not in last_lines[-1] and ':' not in last_lines[-1]:
        hooks_found.add(last_lines[-1][:100])

    async with aiosqlite.connect(DB_PATH) as db:
        for title in hooks_found:
            await db.execute(
                """INSERT INTO foreshadows (project_id, title, description, plant_episode, status, category)
                   VALUES (?,?,?,?,?,?)""",
                (project_id, title, title, episode_num, 'planted', 'cliffhanger'))
        await db.commit()
