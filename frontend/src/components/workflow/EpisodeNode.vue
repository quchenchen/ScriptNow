<!--
  EpisodeNode — the writing stage as one aggregate node: progress bar + a
  heat-strip showing per-episode status. Clicking jumps to the writing stage.
-->
<template>
  <BaseNode
    kind="writing"
    icon="📖"
    title="剧本撰写"
    :badge="`${done}/${total}`"
    :active="isActive"
    :complete="done >= total && total > 0"
    :empty="!episodes.length"
    hide-right
    @activate="$emit('switch')"
  >
    <div class="ep-body">
      <div class="ep-bar">
        <div class="ep-fill" :style="{ width: pct + '%' }"></div>
      </div>
      <div class="ep-strip" v-if="episodes.length">
        <span
          v-for="ep in episodes.slice(0, 32)"
          :key="ep.episode_number"
          :class="['ep-tick', ep.status || 'pending']"
          :title="`EP${ep.episode_number} ${ep.title || ''}`"
        ></span>
        <span v-if="episodes.length > 32" class="ep-more">+{{ episodes.length - 32 }}</span>
      </div>
      <div v-else class="ep-empty">等待架构确认后开始撰写</div>
    </div>
  </BaseNode>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import BaseNode from './BaseNode.vue'

const props = defineProps<{
  episodes: any[]
  total: number
  currentStage: string
}>()
defineEmits<{ (e: 'switch'): void }>()

const done = computed(() => props.episodes.filter(e => e.status === 'done').length)
const pct = computed(() => props.total ? Math.min(100, Math.round(done.value / props.total * 100)) : 0)
const isActive = computed(() => props.currentStage === 'writing')
</script>

<style scoped>
.ep-body { display: flex; flex-direction: column; gap: 6px }
.ep-bar { height: 4px; background: var(--bg-active); border-radius: 2px; overflow: hidden }
.ep-fill { height: 100%; background: linear-gradient(90deg, #22d3ee, #38bdf8); transition: width 0.3s }
.ep-strip { display: flex; flex-wrap: wrap; gap: 2px; align-items: center }
.ep-tick { width: 8px; height: 8px; border-radius: 2px; background: var(--bg-active) }
.ep-tick.done { background: #22d3ee }
.ep-tick.in_progress { background: #fbbf24; animation: pulse 1.5s infinite }
.ep-more { font-size: 10px; color: var(--t5); margin-left: 4px }
.ep-empty { font-size: 11px; color: var(--t5); font-style: italic }
@keyframes pulse { 50% { opacity: 0.4 } }
</style>
