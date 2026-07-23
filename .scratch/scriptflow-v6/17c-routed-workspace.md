# 17C · 可深链工作台与目录选择

- **Status**: done
- **Parent**: 17
- **Blocked by**: 17B

## Acceptance

- [x] Vue Router 路径保存 project / creator space / group / unit
- [x] 刷新恢复当前章/场；浏览器前进后退由同一路由监听恢复
- [x] 新旧项目都从 Dashboard 恢复上次位置
- [x] 一级空间改为创作者语言：作品 / 故事 / 审稿；目录沿用 Novel/Script 单位
- [x] App 拆分出 Dashboard 页面、目录、正文编辑表面和协作概览组件
- [x] 路由与媒介适配测试通过

## 2026-07-16 运行证据

- 项目 10 自动生成 `/projects/10/work/1/8`，选择第一章更新为 `/projects/10/work/1/1`。
- 直接加载并刷新第一章深链后，目录、当前单元和正文都恢复到第一章，没有退回 Dashboard 或最新章。
- 首次实现暴露 Router 初始化与项目列表加载竞态，已通过等待 `router.isReady()` 和 `projectsLoaded` 门槛修复。
- Dashboard 返回后会清空当前项目上下文；再次进入读取该项目最后保存的深链。运行验收从第 2 章返回 Dashboard 后重新进入，恢复 `/projects/10/work/1/2`。
- 前端 13 个测试覆盖路由参数、Dashboard 恢复入口、Novel/Script 术语、目录键盘操作、正文候选边界和协作栏状态。
