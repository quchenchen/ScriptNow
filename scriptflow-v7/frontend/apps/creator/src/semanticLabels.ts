const categoryLabels: Record<string, string> = {
  worldview: '世界观',
  world: '世界观',
  character: '人物',
  arc: '叙事弧线',
  character_arc: '人物弧线',
  event: '关键事件',
  foreshadow: '伏笔',
  theme: '主题',
  thread: '情节线',
  motif: '意象',
}

const anchorLabels: Record<string, string> = {
  'world:era': '时代与历史',
  'world:geography': '地理与空间',
  'world:rules': '世界规则',
  'world:society': '社会结构',
  'world:tone': '氛围与基调',
  'world:medium': '媒介约束',
  'world:pressure': '世界压力',
  'character:protagonist': '核心人物',
  'arc:main': '主要叙事弧线',
  'arc:inner': '人物内在转变',
  'event:inciting': '触发事件',
  'foreshadow:primary': '主要伏笔',
}

const fieldLabels: Record<string, string> = {
  facts: '关键事实',
  forces: '外部压力',
  traits: '人物特征',
  identity: '人物身份',
  stages: '发展阶段',
  points: '转变节点',
  completion: '完成度',
  position: '发生位置',
  plant: '埋设位置',
  payoff: '回收位置',
  status: '状态',
  appearances: '出现位置',
  dramatic_consequence: '戏剧后果',
  readonly: '只读约束',
  project: '所属项目',
}

export function categoryDisplayLabel(kind: string) {
  return categoryLabels[kind] ?? kind
}

export function anchorDisplayLabel(anchorId: string, kind: string) {
  return anchorLabels[anchorId] ?? categoryDisplayLabel(kind)
}

export function fieldDisplayLabel(field: string) {
  return fieldLabels[field] ?? field
}
