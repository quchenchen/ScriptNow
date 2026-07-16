<!--
  SourceNode — pile of uploaded reference documents. Lists filenames and
  indexing status. Users click through to the SourcePanel in storyboard.
-->
<template>
  <BaseNode
    kind="source"
    icon="📚"
    title="参考资料"
    :badge="sources.length ? `${sources.length} 份` : ''"
    :complete="sources.length > 0 && allDone"
    :empty="!sources.length"
    @activate="$emit('open')"
  >
    <div v-if="sources.length" class="src-list">
      <div v-for="s in sources.slice(0, 3)" :key="s.id" class="src-row">
        <span class="src-name">{{ s.filename }}</span>
        <span :class="['src-dot', s.status]"></span>
      </div>
      <div v-if="sources.length > 3" class="src-more">+{{ sources.length - 3 }} 份</div>
    </div>
  </BaseNode>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import BaseNode from './BaseNode.vue'

const props = defineProps<{ sources: any[] }>()
defineEmits<{ (e: 'open'): void }>()

const allDone = computed(() => props.sources.every(s => s.status === 'done'))
</script>

<style scoped>
.src-list { display: flex; flex-direction: column; gap: 3px }
.src-row { display: flex; align-items: center; gap: 4px; font-size: 11px }
.src-name { flex: 1; color: var(--t2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap }
.src-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0 }
.src-dot.done { background: #50c878 }
.src-dot.pending, .src-dot.parsing, .src-dot.indexing { background: #fbbf24; animation: pulse 1.5s infinite }
.src-dot.failed { background: #ff6b6b }
@keyframes pulse { 50% { opacity: 0.3 } }
.src-more { font-size: 10px; color: var(--t5); padding-left: 2px }
</style>
