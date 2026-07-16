<!--
  PitchNode — the project's origin node. Shows source mode + seed / original
  title. First node in every workflow, has no left Handle.
-->
<template>
  <BaseNode
    kind="pitch"
    icon="🌱"
    :title="modeLabel"
    :complete="true"
    hide-left
    @activate="$emit('open')"
  >
    <div class="pitch-body">
      <div v-if="project.original_work" class="pitch-orig">《{{ project.original_work }}》</div>
      <div v-if="project.seed_content" class="pitch-seed">{{ truncate(project.seed_content, 80) }}</div>
      <div v-else class="pitch-seed muted">（无种子内容）</div>
      <div class="pitch-meta">{{ project.target_audience || '未定受众' }} · {{ genreLabel }}</div>
    </div>
  </BaseNode>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import BaseNode from './BaseNode.vue'

const props = defineProps<{ project: any }>()
defineEmits<{ (e: 'open'): void }>()

const modeLabel = computed(() => ({
  original_pitch: '💡 灵感起点',
  original_synopsis: '📝 梗概起点',
  original_theme: '🎯 主题起点',
  adapted: '📚 改编原著',
  rewrite: '✂️ 改写原剧',
}[props.project.source_mode as string] ?? '项目起点'))

const genreLabel = computed(() => {
  try {
    const arr = JSON.parse(props.project.genre || '[]')
    return Array.isArray(arr) && arr.length ? arr.join('·') : '未定题材'
  } catch { return '未定题材' }
})

function truncate(s: string, n: number) {
  if (!s) return ''
  return s.length <= n ? s : s.slice(0, n) + '…'
}
</script>

<style scoped>
.pitch-body { display: flex; flex-direction: column; gap: 4px }
.pitch-orig { font-size: 12px; font-weight: 590; color: var(--t1) }
.pitch-seed { font-size: 11px; color: var(--t2); line-height: 1.5 }
.pitch-seed.muted { color: var(--t5); font-style: italic }
.pitch-meta { font-size: 10px; color: var(--t4); margin-top: 2px }
</style>
