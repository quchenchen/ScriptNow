# Agent 能力与 Skills 后台审查

## 证据

- 改造前：`design-qa-assets/agent-capability-before.png`
- 改造后：`design-qa-assets/agent-skills-final.png`

## 流程与结论

1. 进入旧“Agent / Tool”页面：页面只有模板、空工具组和空挂载矩阵，没有 Skills，也没有概念解释。状态：不合格。
2. 选择 Agent 角色：改造后用中文职责解释四个角色，并展示本领域 Skill 和 Tool Group 数量。状态：通过。
3. 切换小说/剧本产品域：Skills 按独立领域装配，平台通用 Skill 两域共享。状态：通过。
4. 查看 Skills 技能库：真实读取仓库 `SKILL.md` 的名称、描述、领域、参考资源和挂载状态。状态：通过。
5. 查看执行能力：页面明确区分 Skill 方法论、Tool 执行能力和 MCP 外部能力；工具组为空时显示可行动的真实空状态。状态：通过。

## 运行时缺陷修复

旧映射使用 `ideation / structure`，而运行时角色使用 `director / architect`，导致两个角色无法取得领域 Skill。映射已统一为运行时角色键，并加入回归测试。

## 可访问性检查

- 角色、领域和导航均使用原生按钮，可键盘聚焦。
- 领域选择与已挂载状态不只依赖颜色，同时有文字标签。
- Skills 卡片描述仍来自英文 frontmatter；这是内容本地化问题，不影响操作，但后续应逐步提供中文说明。
- 截图无法验证完整键盘顺序、屏幕阅读器朗读和对比度数值，需要独立自动化/人工无障碍测试。
