import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import SourceDistillationPanel from './SourceDistillationPanel.vue'

function json(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('SourceDistillationPanel', () => {
  afterEach(() => vi.restoreAllMocks())

  it('shows the provider scope and requires explicit consent before execution', async () => {
    const fetch = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const path = String(input)
      if (path.endsWith('/source-distillations/latest')) return json(null)
      if (path.endsWith('/files')) return json([{ id: 'file-1', original_name: 'source.docx', media_type: 'application/docx', byte_size: 100, status: 'ready' }])
      if (path.endsWith('/source-distillations') && init?.method === 'POST') return json({ id: 'distill-1', status: 'running', pass_key: 'inventory', checkpoint: { processed_chunk_ids: [] }, coverage: { total_chunks: 10 }, candidate: null })
      if (path.endsWith('/execution-preflight')) return json({ provider_key: 'aliyun', model_key: 'deepseek-v4-pro', runtime_connected: true, consent_version: 'source-processing-v1', purpose: ['证据提取'], sources: [{ id: 'file-1', name: 'source.docx', byte_size: 100 }], processed_chunks: 0, total_chunks: 10 })
      if (path.endsWith('/execute')) return json({ run_id: 'run-1' })
      if (path.endsWith('/source-distillations/distill-1')) return json({ id: 'distill-1', status: 'ready', pass_key: 'human_decision', checkpoint: { processed_chunk_ids: Array(10).fill('chunk') }, coverage: { total_chunks: 10 }, candidate: { id: 'profile-1', version: 1, decision: 'candidate', profile: { relationship_engine: 'trust under pressure' }, conflicts: [], exclusions: ['author imitation'], evidence: [] } })
      if (path.endsWith('/runs/run-1')) return json({ status: 'waiting' })
      throw new Error(`Unexpected request: ${path}`)
    })
    vi.stubGlobal('fetch', fetch)
    const wrapper = mount(SourceDistillationPanel, { props: { projectId: 'project-1' } })
    await flushPromises()

    await wrapper.get('.source-profile-start').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('aliyun')
    expect(wrapper.text()).toContain('source.docx')
    const authorize = wrapper.findAll('.source-profile-actions button')[1]
    expect(authorize.attributes('disabled')).toBeDefined()

    await wrapper.get('.source-consent input').setValue(true)
    expect(authorize.attributes('disabled')).toBeUndefined()
    await authorize.trigger('click')
    await flushPromises()
    const executeCall = fetch.mock.calls.find(([input]) => String(input).endsWith('/execute'))
    expect(JSON.parse(String(executeCall?.[1]?.body))).toMatchObject({
      external_processing_consent: true,
      consent_version: 'source-processing-v1',
    })
    expect(wrapper.text()).toContain('trust under pressure')
  })
})
