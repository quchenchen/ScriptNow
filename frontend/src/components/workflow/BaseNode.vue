<!--
  BaseNode — a lean, opinionated wrapper for every ScriptFlow canvas node.

  Every node in the workflow shares the same skeleton: a header row (icon +
  title + optional badge), a body slot for stage-specific content, and
  ``<Handle>`` connection points on the left/right. Individual node
  components (PitchNode, IdeationNode, ...) supply the ``kind``, colour
  accent, and body slot; the routing/interaction is unified here so a change
  in styling touches one file, not ten.
-->
<template>
  <div
    class="wf-node"
    :class="[`kind-${kind}`, { active, complete, empty }]"
    @click="$emit('activate')"
  >
    <Handle v-if="!hideLeft" type="target" :position="Position.Left" />
    <div class="wf-node-head">
      <span class="wf-node-icon">{{ icon }}</span>
      <span class="wf-node-title">{{ title }}</span>
      <span v-if="badge" class="wf-node-badge">{{ badge }}</span>
    </div>
    <div class="wf-node-body">
      <slot>
        <span v-if="empty" class="wf-node-empty">尚未生成</span>
      </slot>
    </div>
    <Handle v-if="!hideRight" type="source" :position="Position.Right" />
  </div>
</template>

<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'

defineProps<{
  kind: 'pitch' | 'source' | 'ideation' | 'structure' | 'writing' | 'review' | 'asset'
  icon: string
  title: string
  badge?: string
  active?: boolean
  complete?: boolean
  empty?: boolean
  hideLeft?: boolean
  hideRight?: boolean
}>()

defineEmits<{ (e: 'activate'): void }>()
</script>

<style scoped>
.wf-node {
  min-width: 220px;
  max-width: 300px;
  background: var(--bg-surface);
  border: 1px solid var(--bs);
  border-radius: 10px;
  padding: 10px 12px;
  cursor: pointer;
  transition: all 0.15s;
  font-size: 12px;
  color: var(--t1);
}
.wf-node:hover { border-color: var(--bw); background: #22242a }
.wf-node.active { border-color: var(--accent); box-shadow: 0 0 0 2px rgba(88,166,255,0.2) }
.wf-node.complete .wf-node-icon { filter: drop-shadow(0 0 3px rgba(80,200,120,0.5)) }
.wf-node.empty { opacity: 0.6 }

.wf-node-head { display: flex; align-items: center; gap: 6px; margin-bottom: 6px }
.wf-node-icon { font-size: 16px; flex-shrink: 0 }
.wf-node-title { font-weight: 590; font-size: 13px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap }
.wf-node-badge { font-size: 10px; padding: 1px 6px; background: var(--bg-active); color: var(--t3); border-radius: 4px }

.wf-node-body { font-size: 11px; color: var(--t3); line-height: 1.5; min-height: 20px }
.wf-node-empty { color: var(--t5); font-style: italic }

/* colour accents per kind */
.wf-node.kind-pitch    { border-left: 3px solid #c084fc }
.wf-node.kind-source   { border-left: 3px solid #38bdf8 }
.wf-node.kind-ideation { border-left: 3px solid #fbbf24 }
.wf-node.kind-structure { border-left: 3px solid #f472b6 }
.wf-node.kind-writing  { border-left: 3px solid #22d3ee }
.wf-node.kind-review   { border-left: 3px solid #a3e635 }
.wf-node.kind-asset    { border-left: 3px solid #94a3b8 }
</style>
