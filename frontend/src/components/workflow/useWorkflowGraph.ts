/**
 * useWorkflowGraph — assemble the ScriptFlow project into vue-flow's nodes/edges,
 * with dagre-driven left-to-right auto-layout.
 *
 * Kept out of ``WorkflowCanvas.vue`` so unit tests can drive the graph shape
 * without booting Vue. Pure functions everywhere except the reactive
 * wrapper at the end.
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import dagre from '@dagrejs/dagre'
import type { Edge, Node } from '@vue-flow/core'

export type StageKey =
  | 'pitch' | 'source' | 'ideation' | 'structure'
  | 'writing' | 'review' | 'polish' | 'assets' | 'prompts'

export interface GraphInput {
  project: any
  sources: any[]
  plans: any[]
  structureCards: any[]
  structureConfirmed: boolean
  episodes: any[]
  currentStage: string
  pipelineStages: { key: string; label: string }[]
}

const NODE_W = 240
const NODE_H = 100

/** Build the raw node list (types + data) before laying them out. */
export function buildNodes(input: GraphInput): Node[] {
  const nodes: Node[] = [
    {
      id: 'pitch',
      type: 'pitch',
      position: { x: 0, y: 0 },
      data: { project: input.project },
      draggable: true,
    },
  ]

  if (input.sources.length) {
    nodes.push({
      id: 'source',
      type: 'source',
      position: { x: 0, y: 0 },
      data: { sources: input.sources },
      draggable: true,
    })
  }

  // Stage nodes — only those the project's pipeline actually has
  for (const stage of ['ideation', 'structure'] as StageKey[]) {
    if (!input.pipelineStages.some(s => s.key === stage)) continue
    nodes.push({
      id: `stage-${stage}`,
      type: 'stage',
      position: { x: 0, y: 0 },
      data: {
        stage,
        currentStage: input.currentStage,
        plans: input.plans,
        structureCards: input.structureCards,
        structureConfirmed: input.structureConfirmed,
      },
      draggable: true,
    })
  }

  // Writing aggregates into its own node type
  if (input.pipelineStages.some(s => s.key === 'writing')) {
    nodes.push({
      id: 'stage-writing',
      type: 'episode',
      position: { x: 0, y: 0 },
      data: {
        episodes: input.episodes,
        total: input.project.total_episodes || 80,
        currentStage: input.currentStage,
      },
      draggable: true,
    })
  }

  // Optional downstream stages
  for (const stage of ['review', 'polish', 'assets', 'prompts'] as StageKey[]) {
    if (!input.pipelineStages.some(s => s.key === stage)) continue
    nodes.push({
      id: `stage-${stage}`,
      type: 'stage',
      position: { x: 0, y: 0 },
      data: {
        stage,
        currentStage: input.currentStage,
        plans: input.plans,
        structureCards: input.structureCards,
        structureConfirmed: input.structureConfirmed,
      },
      draggable: true,
    })
  }

  return nodes
}

/** Straight edges: pitch → source → ideation → structure → writing → review → ... */
export function buildEdges(nodes: Node[]): Edge[] {
  const edges: Edge[] = []
  const ids = nodes.map(n => n.id)

  if (ids.includes('source')) edges.push(mkEdge('pitch', 'source'))
  const preIdeation = ids.includes('source') ? 'source' : 'pitch'
  if (ids.includes('stage-ideation')) edges.push(mkEdge(preIdeation, 'stage-ideation'))

  const chain = ['stage-ideation', 'stage-structure', 'stage-writing',
                 'stage-review', 'stage-polish', 'stage-assets', 'stage-prompts']
  for (let i = 0; i < chain.length - 1; i++) {
    if (ids.includes(chain[i]) && ids.includes(chain[i + 1])) {
      edges.push(mkEdge(chain[i], chain[i + 1]))
    }
  }
  return edges
}

function mkEdge(from: string, to: string): Edge {
  return {
    id: `${from}->${to}`,
    source: from,
    target: to,
    animated: false,
    style: { stroke: '#4b5563', strokeWidth: 1.5 },
  }
}

/** Run dagre for a left-to-right layout, mutating positions on a fresh array. */
export function layoutNodes(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'LR', nodesep: 40, ranksep: 80 })

  nodes.forEach(n => g.setNode(n.id, { width: NODE_W, height: NODE_H }))
  edges.forEach(e => g.setEdge(e.source, e.target))

  dagre.layout(g)

  return nodes.map(n => {
    const pos = g.node(n.id)
    return {
      ...n,
      position: pos ? { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 } : n.position,
    }
  })
}

/** Reactive wrapper — the ``input`` ref feeds through buildNodes+buildEdges+layout. */
export function useWorkflowGraph(input: Ref<GraphInput> | ComputedRef<GraphInput>) {
  const nodes = computed(() => {
    const raw = buildNodes(input.value)
    const edges = buildEdges(raw)
    return layoutNodes(raw, edges)
  })
  const edges = computed(() => buildEdges(buildNodes(input.value)))
  return { nodes, edges }
}
