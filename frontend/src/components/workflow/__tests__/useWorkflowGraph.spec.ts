/**
 * Tests for the workflow graph builder.
 */
import { describe, it, expect } from 'vitest'
import { buildNodes, buildEdges, layoutNodes, type GraphInput } from '../useWorkflowGraph'

function baseInput(overrides: Partial<GraphInput> = {}): GraphInput {
  return {
    project: { id: 1, source_mode: 'original_pitch', total_episodes: 80 },
    sources: [],
    plans: [],
    structureCards: [],
    structureConfirmed: false,
    episodes: [],
    currentStage: 'ideation',
    pipelineStages: [
      { key: 'ideation', label: '灵感孵化' },
      { key: 'structure', label: '故事架构' },
      { key: 'writing', label: '剧本撰写' },
      { key: 'review', label: '质量审核' },
    ],
    ...overrides,
  }
}

describe('buildNodes', () => {
  it('always emits a pitch node', () => {
    const nodes = buildNodes(baseInput())
    expect(nodes[0]).toMatchObject({ id: 'pitch', type: 'pitch' })
  })

  it('omits source node when there are no uploads', () => {
    const nodes = buildNodes(baseInput())
    expect(nodes.find(n => n.id === 'source')).toBeUndefined()
  })

  it('includes source node when at least one upload exists', () => {
    const nodes = buildNodes(baseInput({
      sources: [{ id: 1, filename: 'a.txt', status: 'done' }],
    }))
    expect(nodes.find(n => n.id === 'source')).toBeTruthy()
  })

  it('honours pipelineStages — only wanted stages appear', () => {
    const nodes = buildNodes(baseInput({
      pipelineStages: [
        { key: 'ideation', label: '灵感' },
        { key: 'writing', label: '撰写' },
      ],
    }))
    const ids = nodes.map(n => n.id)
    expect(ids).toContain('stage-ideation')
    expect(ids).toContain('stage-writing')
    expect(ids).not.toContain('stage-structure')
    expect(ids).not.toContain('stage-review')
  })

  it('writing gets its own aggregate "episode" type', () => {
    const nodes = buildNodes(baseInput())
    const writing = nodes.find(n => n.id === 'stage-writing')
    expect(writing?.type).toBe('episode')
  })

  it('threads relevant per-stage data through data payload', () => {
    const nodes = buildNodes(baseInput({
      plans: [{ id: 'A' }, { id: 'B' }],
      currentStage: 'structure',
    }))
    const ideation = nodes.find(n => n.id === 'stage-ideation')
    expect(ideation?.data.plans).toHaveLength(2)
    expect(ideation?.data.currentStage).toBe('structure')
  })
})

describe('buildEdges', () => {
  it('connects pitch → source → ideation → structure → writing → review', () => {
    const nodes = buildNodes(baseInput({
      sources: [{ id: 1, filename: 'x', status: 'done' }],
    }))
    const edges = buildEdges(nodes)
    const ids = edges.map(e => e.id)
    expect(ids).toContain('pitch->source')
    expect(ids).toContain('source->stage-ideation')
    expect(ids).toContain('stage-ideation->stage-structure')
    expect(ids).toContain('stage-structure->stage-writing')
    expect(ids).toContain('stage-writing->stage-review')
  })

  it('routes pitch directly to ideation when no sources', () => {
    const nodes = buildNodes(baseInput())
    const edges = buildEdges(nodes)
    expect(edges.map(e => e.id)).toContain('pitch->stage-ideation')
    expect(edges.map(e => e.id)).not.toContain('pitch->source')
  })

  it('skips edges where either endpoint is absent', () => {
    const nodes = buildNodes(baseInput({
      pipelineStages: [{ key: 'ideation', label: 'X' }],
    }))
    const edges = buildEdges(nodes)
    expect(edges.every(e => e.id !== 'stage-ideation->stage-structure')).toBe(true)
  })
})

describe('layoutNodes', () => {
  it('positions nodes with dagre — pitch on the left, later stages to the right', () => {
    const input = baseInput({
      sources: [{ id: 1, filename: 'x', status: 'done' }],
    })
    const raw = buildNodes(input)
    const edges = buildEdges(raw)
    const laid = layoutNodes(raw, edges)

    const pitch = laid.find(n => n.id === 'pitch')!
    const writing = laid.find(n => n.id === 'stage-writing')!
    expect(pitch.position.x).toBeLessThan(writing.position.x)
  })

  it('does not blow up on empty edge list', () => {
    const raw = buildNodes(baseInput())
    const laid = layoutNodes(raw, [])
    expect(laid.length).toBe(raw.length)
  })
})
