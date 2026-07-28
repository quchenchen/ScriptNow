import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useScriptStore } from './script'

const emptyState = {
  phase: 'story_map_adopted',
  script_format: 'chinese',
  story_cores: [],
  blueprint: null,
  blueprint_candidates: [],
  story_map: { id: 'map-1', version: 1, episodes: [] },
  story_map_candidates: [],
  documents: [],
}

describe('script scene decisions', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.stubGlobal('document', { cookie: '' })
  })

  afterEach(() => vi.unstubAllGlobals())

  it('generates a scene candidate through the background run without adopting it', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        id: 'run-1',
        run_id: 'run-1',
        operation_id: 'operation-1',
        creative_session_id: 'session-1',
        status: 'queued',
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        id: 'run-1',
        status: 'succeeded',
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(emptyState), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await useScriptStore().generateSceneCandidate('project-1', 'scene-1')

    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(String(fetchMock.mock.calls[0][0])).toContain('/scenes/scene-1/generate')
    expect(String(fetchMock.mock.calls[0][0])).toContain('background=true')
    expect(String(fetchMock.mock.calls[1][0])).toContain('/runs/run-1')
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/adopt'))).toBe(false)
  })
})
