import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ReviewPanel from './ReviewPanel.vue'

describe('ReviewPanel performance guard', () => {
  afterEach(() => vi.restoreAllMocks())

  it('virtualizes 200 findings to a bounded DOM window', async () => {
    const findings = Array.from({ length: 200 }, (_, index) => ({
      id: `finding-${index}`, project_id: 'project', unit_id: 'scene-1', base_revision_id: 'revision',
      element_id: 'paragraph-1', domain: 'character', severity: 'major', source: 'ai', author: 'reviewer',
      anchor_type: 'character', anchor_id: 'character:1', anchor_note: '', original_excerpt: 'text',
      diagnosis: `diagnosis ${index}`, suggestion: 'suggestion', suggested_patch: {}, confidence: 'high',
      status: 'open', created_at: '2026-07-20T00:00:00Z',
    }))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(findings), { status: 200, headers: { 'Content-Type': 'application/json' } })))
    const wrapper = mount(ReviewPanel, {
      global: { plugins: [createPinia()] },
      props: { projectId: 'project', medium: 'script', unitId: 'scene-1', revisionId: 'revision', elements: [], anchors: [] },
    })
    await flushPromises()
    expect(wrapper.get('h3').text()).toContain('200')
    expect(wrapper.findAll('.finding-card')).toHaveLength(10)
    expect(wrapper.find('.finding-list').attributes('role')).toBe('list')
  })
})
