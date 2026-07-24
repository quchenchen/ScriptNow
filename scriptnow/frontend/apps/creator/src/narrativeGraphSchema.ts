export const narrativeNodeTypes = [
  'character',
  'event',
  'organization',
  'location',
  'object',
  'concept',
  'relationship',
  'story_thread',
] as const

export type NarrativeNodeType = typeof narrativeNodeTypes[number] | 'chapter'

export const narrativeRelationTypes = [
  'causal',
  'emotional',
  'conflict',
  'foreshadowing',
  'constraint',
  'affiliation',
] as const

export type NarrativeRelationType = typeof narrativeRelationTypes[number]

export function canonicalNarrativeRelationType(value: unknown): NarrativeRelationType | undefined {
  if (typeof value !== 'string') return undefined
  const normalized = value.trim().toLowerCase().replaceAll(/[\s-]+/g, '_')
  if ((narrativeRelationTypes as readonly string[]).includes(normalized)) {
    return normalized as NarrativeRelationType
  }
  if (/conflict|oppose|threat|reject|attack|kill|betray|rival/.test(normalized)) return 'conflict'
  if (/cause|lead|trigger|result|change|reveal|discover|find|learn|enable|prevent|progress/.test(normalized)) return 'causal'
  if (/bond|love|trust|protect|family|kin|emotion/.test(normalized)) return 'emotional'
  if (/foreshadow|setup|payoff|promise|echo|motif/.test(normalized)) return 'foreshadowing'
  if (/rule|govern|constrain|require|forbid|permit|limit/.test(normalized)) return 'constraint'
  if (/member|belong|locat|contain|part.?of|affiliat|participat|ally/.test(normalized)) return 'affiliation'
  return undefined
}

const nodeTypeAliases: Record<string, NarrativeNodeType> = {
  chapter: 'chapter',
  character: 'character',
  person: 'character',
  event: 'event',
  plot_event: 'event',
  organization: 'organization',
  organisation: 'organization',
  faction: 'organization',
  group: 'organization',
  location: 'location',
  place: 'location',
  object: 'object',
  artifact: 'object',
  prop: 'object',
  concept: 'concept',
  motif: 'concept',
  theme: 'concept',
  world_rule: 'concept',
  worldrule: 'concept',
  rule: 'concept',
  relationship: 'relationship',
  relation: 'relationship',
  story_thread: 'story_thread',
  foreshadow: 'story_thread',
  setup: 'story_thread',
  promise: 'story_thread',
  mystery: 'story_thread',
}

export function canonicalNarrativeNodeType(value: unknown): NarrativeNodeType | undefined {
  if (typeof value !== 'string') return undefined
  return nodeTypeAliases[value.trim().toLowerCase().replaceAll(/[\s-]+/g, '_')]
}

const nodeTypeLabels: Record<NarrativeNodeType, readonly [string, string]> = {
  chapter: ['章节', 'Chapter'],
  character: ['人物', 'Character'],
  event: ['事件', 'Event'],
  organization: ['组织 / 群体', 'Organization / group'],
  location: ['地点', 'Location'],
  object: ['关键物件', 'Story object'],
  concept: ['观念 / 规则', 'Concept / rule'],
  relationship: ['关系', 'Relationship'],
  story_thread: ['叙事线索', 'Story thread'],
}

const relationTypeLabels: Record<NarrativeRelationType, readonly [string, string]> = {
  causal: ['推进 / 因果', 'Progression / cause'],
  emotional: ['人物 / 情感', 'Character / emotion'],
  conflict: ['冲突 / 对抗', 'Conflict / opposition'],
  foreshadowing: ['伏笔 / 回响', 'Setup / payoff'],
  constraint: ['规则 / 约束', 'Rule / constraint'],
  affiliation: ['归属 / 参与', 'Affiliation / participation'],
}

export function narrativeNodeTypeLabel(type: NarrativeNodeType, english: boolean) {
  return nodeTypeLabels[type][english ? 1 : 0]
}

export function narrativeRelationTypeLabel(type: NarrativeRelationType, english: boolean) {
  return relationTypeLabels[type][english ? 1 : 0]
}
