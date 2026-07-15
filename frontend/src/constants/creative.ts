/**
 * Shared creative-preference option lists.
 *
 * Drives both project-creation dialog (Dashboard.vue) and the in-workspace
 * ediable preferences panel (useWorkspace.ts). One source of truth so
 * the two surfaces do not drift.
 */
export const genreOptions: readonly string[] = [
  '悬疑', '科幻', '情感', '霸总', '古装', '玄幻', '都市', '恐怖', '喜剧',
] as const

export const styleOptions: readonly string[] = [
  '快节奏', '慢热文艺', '爽文', '现实主义', '烧脑', '轻松治愈', '黑色幽默',
] as const
