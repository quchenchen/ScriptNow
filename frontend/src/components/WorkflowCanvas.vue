<!--
  WorkflowCanvas — the "workflow" tab of a project's Workspace. Wraps
  vue-flow to render project structure as a DAG: pitch → sources → stages
  → episodes → downstream. Clicking a node emits ``switch-stage`` so the
  parent can flip to Storyboard view at that stage.
-->
<template>
  <div class="wf-canvas">
    <VueFlow
      :nodes="nodes"
      :edges="edges"
      :nodes-draggable="true"
      :nodes-connectable="false"
      :elements-selectable="true"
      :edges-updatable="false"
      :min-zoom="0.3"
      :max-zoom="2"
      fit-view-on-init
    >
      <template #node-pitch="props">
        <PitchNode :project="props.data.project" @open="onOpenPitch" />
      </template>
      <template #node-source="props">
        <SourceNode :sources="props.data.sources" @open="onOpenSource" />
      </template>
      <template #node-stage="props">
        <StageNode
          :stage="props.data.stage"
          :current-stage="props.data.currentStage"
          :plans="props.data.plans"
          :structure-cards="props.data.structureCards"
          :structure-confirmed="props.data.structureConfirmed"
          @switch="onSwitchStage"
        />
      </template>
      <template #node-episode="props">
        <EpisodeNode
          :episodes="props.data.episodes"
          :total="props.data.total"
          :current-stage="props.data.currentStage"
          @switch="onSwitchStage('writing')"
        />
      </template>
      <Background pattern-color="#2a2a2e" :gap="20" />
      <Controls />
      <MiniMap
        :node-color="miniMapNodeColor"
        :mask-color="'rgba(0,0,0,0.7)'"
        pannable
        zoomable
      />
    </VueFlow>
    <!-- Keyboard hint overlay (bottom-left) -->
    <div class="wf-hint">
      <kbd>⌘</kbd>+<kbd>1</kbd> 工作流 · <kbd>⌘</kbd>+<kbd>2</kbd> 故事板
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { VueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

import PitchNode from './workflow/PitchNode.vue'
import SourceNode from './workflow/SourceNode.vue'
import StageNode from './workflow/StageNode.vue'
import EpisodeNode from './workflow/EpisodeNode.vue'
import { useWorkflowGraph, type GraphInput } from './workflow/useWorkflowGraph'

const props = defineProps<{
  project: any
  sources: any[]
  plans: any[]
  structureCards: any[]
  structureConfirmed: boolean
  episodes: any[]
  currentStage: string
  pipelineStages: { key: string; label: string }[]
}>()

const emit = defineEmits<{
  (e: 'switch-stage', stage: string): void
  (e: 'open-pitch'): void
  (e: 'open-source'): void
  (e: 'toggle-view'): void
}>()

const graphInput = computed<GraphInput>(() => ({
  project: props.project,
  sources: props.sources,
  plans: props.plans,
  structureCards: props.structureCards,
  structureConfirmed: props.structureConfirmed,
  episodes: props.episodes,
  currentStage: props.currentStage,
  pipelineStages: props.pipelineStages,
}))

const { nodes, edges } = useWorkflowGraph(graphInput)

function onSwitchStage(stage: string) { emit('switch-stage', stage) }
function onOpenPitch() { emit('open-pitch') }
function onOpenSource() { emit('open-source') }

// MiniMap node colours keyed by node type
function miniMapNodeColor(node: any) {
  const colours: Record<string, string> = {
    pitch: '#c084fc',
    source: '#38bdf8',
    stage: '#fbbf24',
    episode: '#22d3ee',
  }
  return colours[node.type] || '#4b5563'
}

// Keyboard shortcut: Cmd/Ctrl+1 = workflow, Cmd/Ctrl+2 = storyboard
function handleKey(e: KeyboardEvent) {
  if (!(e.metaKey || e.ctrlKey)) return
  if (e.key === '1' || e.key === '2') {
    e.preventDefault()
    emit('toggle-view')
  }
}
onMounted(() => window.addEventListener('keydown', handleKey))
onUnmounted(() => window.removeEventListener('keydown', handleKey))
</script>

<style scoped>
.wf-canvas {
  width: 100%;
  height: 100%;
  background: var(--bg-panel);
  position: relative;
}
.wf-hint {
  position: absolute;
  bottom: 10px;
  left: 10px;
  font-size: 10px;
  color: var(--t5);
  pointer-events: none;
  user-select: none;
}
.wf-hint kbd {
  display: inline-block;
  padding: 1px 4px;
  border: 1px solid var(--border-subtle);
  border-radius: 3px;
  background: var(--bg-surface);
  font-size: 9px;
  font-family: inherit;
  color: var(--t3);
}
/* Override vue-flow's default theme for our dark shell */
:deep(.vue-flow__background) { background: var(--bg-panel) }
:deep(.vue-flow__controls) {
  background: var(--bg-surface);
  border: 1px solid var(--bs);
  border-radius: 6px;
  box-shadow: none;
}
:deep(.vue-flow__controls-button) {
  background: transparent;
  border: none;
  color: var(--t2);
  fill: var(--t2);
}
:deep(.vue-flow__controls-button:hover) { background: var(--bg-active) }
:deep(.vue-flow__edge-path) { stroke: #4b5563 }
:deep(.vue-flow__handle) {
  width: 8px; height: 8px;
  background: var(--bg-active);
  border: 1px solid var(--bs);
}
:deep(.vue-flow__handle-connecting) { background: var(--accent) }
/* MiniMap theming */
:deep(.vue-flow__minimap) {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
}
</style>
