export const CREATIVE_ROLE_LABELS: Record<string, string> = {
  director: '灵感导演',
  architect: '故事建筑师',
  writer: '主笔',
  reviewer: '审读编辑',
  editor: '审读编辑',
}

export function creativeRoleLabel(roleKey: string, fallback?: string) {
  return CREATIVE_ROLE_LABELS[roleKey] ?? fallback ?? roleKey
}
