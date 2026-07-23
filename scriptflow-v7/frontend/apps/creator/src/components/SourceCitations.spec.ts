import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import SourceCitations from './SourceCitations.vue'

describe('SourceCitations', () => {
  afterEach(() => vi.restoreAllMocks())

  it('browses and locates an indexed source excerpt', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify([{
      chunk_id: 'chunk-1', source_file_id: 'file-1', source_name: '原著.txt', ordinal: 0,
      excerpt: '那封被隐藏多年的信终于回来了。', score: 0,
    }]), { status: 200, headers: { 'Content-Type': 'application/json' } })))
    const wrapper = mount(SourceCitations, { props: { projectId: 'project-1' } })
    await flushPromises()
    expect(wrapper.text()).toContain('原著.txt')
    expect(wrapper.find('blockquote').exists()).toBe(false)
    await wrapper.get('.source-hit').trigger('click')
    expect(wrapper.get('blockquote').text()).toContain('隐藏多年的信')
    expect(wrapper.get('.source-hit').attributes('aria-expanded')).toBe('true')
  })
})
