import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, describe, expect, it, vi } from 'vitest'

import NovelQualityPanel from './NovelQualityPanel.vue'
import { useDockStore } from '../stores/dock'

function json(value: unknown) {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

const dimensions = [
  'character_agency', 'scene_causality', 'relationship_progression', 'narrative_voice',
  'continuity', 'source_boundary', 'chapter_propulsion', 'prose_texture',
].map((dimension) => ({
  dimension,
  verdict: dimension === 'narrative_voice' ? 'revise' : 'pass',
  score: dimension === 'narrative_voice' ? 3 : 5,
  evidence: [`Evidence for ${dimension}`],
  diagnosis: `Diagnosis for ${dimension}`,
  repair: `Repair ${dimension}`,
}))

describe('NovelQualityPanel', () => {
  afterEach(() => vi.restoreAllMocks())

  it('shows only the report bound to the current revision and hands the decision to the review editor', async () => {
    const fetch = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const path = String(input)
      if (path.endsWith('/quality-reports') && !init?.method) return json([
        { id: 'old', revision_id: 'revision-old', rubric_version: 'v1', overall_status: 'ready', maturity_score: 100, summary: 'Old report', dimensions },
        { id: 'current', revision_id: 'revision-2', rubric_version: 'novel-chapter-quality-v1', overall_status: 'revision_required', maturity_score: 95, summary: 'Voice needs revision.', dimensions },
      ])
      throw new Error(`Unexpected request: ${path}`)
    })
    vi.stubGlobal('fetch', fetch)
    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(NovelQualityPanel, {
      props: { projectId: 'project-1', chapterId: 'chapter-1', revisionId: 'revision-2' },
      global: { plugins: [pinia] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('95/100')
    expect(wrapper.text()).toContain('Voice needs revision.')
    expect(wrapper.text()).not.toContain('Old report')
    expect(wrapper.text()).toContain('叙述声音')
    await wrapper.get('button').trigger('click')
    const dock = useDockStore()
    expect(dock.role).toBe('reviewer')
    expect(dock.reviewCheckpoint).toMatchObject({
      key: 'novel_document:chapter-1:revision-2',
      action: 'novel_document.review',
      focus: { medium: 'novel', unit_id: 'chapter-1' },
    })
    expect(fetch).toHaveBeenCalledTimes(1)
  })
})
