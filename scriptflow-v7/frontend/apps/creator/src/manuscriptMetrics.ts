export type ManuscriptMetrics = {
  count: number
  unit: 'words' | '字'
}

const ENGLISH_WORD = /[\p{L}\p{N}]+(?:['’\-][\p{L}\p{N}]+)*/gu
const CHINESE_UNIT = /[\p{Script=Han}]|[A-Za-z0-9]+/gu

export function manuscriptMetrics(
  blocks: Array<{ text: string }>,
  creativeLanguage = 'zh-CN',
): ManuscriptMetrics {
  const text = blocks.map((block) => block.text).join('\n')
  const isEnglish = creativeLanguage.toLowerCase().startsWith('en')
  return {
    count: (text.match(isEnglish ? ENGLISH_WORD : CHINESE_UNIT) ?? []).length,
    unit: isEnglish ? 'words' : '字',
  }
}

export function manuscriptProgress(
  blocks: Array<{ text: string }>,
  creativeLanguage: string,
  target: number | undefined,
) {
  const metrics = manuscriptMetrics(blocks, creativeLanguage)
  if (!target) return { ...metrics, ratio: null, status: 'unknown' as const }
  const ratio = metrics.count / target
  return {
    ...metrics,
    ratio,
    status: ratio > 1.2 ? 'over' as const : ratio < 0.8 ? 'under' as const : 'on-target' as const,
  }
}
