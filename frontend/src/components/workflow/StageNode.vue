<!--
  StageNode — pipeline stage (ideation / structure / review / polish /
  assets / prompts). Clicking switches storyboard view to this stage.
-->
<template>
  <BaseNode
    :kind="kind"
    :icon="icon"
    :title="label"
    :badge="statusLabel"
    :active="isActive"
    :complete="isComplete"
    :empty="isEmpty"
    @activate="$emit('switch', stage)"
  >
    <div class="stage-body">
      <div class="stage-desc">{{ desc }}</div>
      <div v-if="detail" class="stage-detail">{{ detail }}</div>
    </div>
  </BaseNode>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import BaseNode from './BaseNode.vue'

const props = defineProps<{
  stage: string
  currentStage: string
  plans?: any[]
  structureCards?: any[]
  structureConfirmed?: boolean
}>()

defineEmits<{ (e: 'switch', stage: string): void }>()

const meta = computed<{ label: string; icon: string; desc: string; kind: any }>(() => ({
  ideation:  { label: '灵感孵化', icon: '💡', desc: '生成 3 个差异化方案', kind: 'ideation' },
  structure: { label: '故事架构', icon: '📐', desc: '三幕 · 角色 · 伏笔', kind: 'structure' },
  review:    { label: '质量审核', icon: '🔍', desc: 'A/B/C/D 分维度评分', kind: 'review' },
  polish:    { label: '润色定稿', icon: '✨', desc: '文字精修', kind: 'review' },
  assets:    { label: '资产提取', icon: '📦', desc: '角色/场景/道具', kind: 'asset' },
  prompts:   { label: '提示词', icon: '🎥', desc: 'Seedance 视频提示', kind: 'asset' },
}[props.stage] ?? { label: props.stage, icon: '•', desc: '', kind: 'asset' }))

const label = computed(() => meta.value.label)
const icon = computed(() => meta.value.icon)
const desc = computed(() => meta.value.desc)
const kind = computed(() => meta.value.kind)

const isActive = computed(() => props.currentStage === props.stage)

const isComplete = computed(() => {
  if (props.stage === 'ideation') return (props.plans?.length ?? 0) > 0
  if (props.stage === 'structure') return !!props.structureConfirmed
  return false
})
const isEmpty = computed(() => !isActive.value && !isComplete.value)

const statusLabel = computed(() => {
  if (isComplete.value) return '✓ 已完成'
  if (isActive.value) return '进行中'
  return ''
})

const detail = computed(() => {
  if (props.stage === 'ideation' && props.plans?.length) return `${props.plans.length} 个方案`
  if (props.stage === 'structure' && props.structureCards?.length) return `${props.structureCards.length} 张架构卡`
  return ''
})
</script>

<style scoped>
.stage-body { display: flex; flex-direction: column; gap: 3px }
.stage-desc { font-size: 11px; color: var(--t3) }
.stage-detail { font-size: 10px; color: var(--t4); margin-top: 2px }
</style>
