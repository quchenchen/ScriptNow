import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { selectChapterDocument, useNovelStore } from './novel'

const emptyState = {
  phase: 'story_map_adopted',
  story_cores: [],
  blueprint: null,
  blueprint_candidates: [],
  story_map: { id: 'map-1', version: 1, volumes: [] },
  story_map_candidates: [],
  documents: [],
}

describe('novel chapter decisions', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.stubGlobal('document', { cookie: '' })
  })
  afterEach(() => vi.unstubAllGlobals())

  it('generates a chapter candidate without silently adopting it', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'revision-1', status: 'candidate' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(emptyState), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await useNovelStore().generateChapter('project-1', 'chapter-1')

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(String(fetchMock.mock.calls[0][0])).toContain('/chapters/chapter-1/generate')
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/adopt'))).toBe(false)
  })

  it('can revise a specific candidate without overwriting or adopting it', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'revision-4', status: 'candidate' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(emptyState), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await useNovelStore().generateChapter('project-1', 'chapter-1', {
      feedback: 'Condense to 1200 words.',
      sourceRevisionId: 'revision-3',
    })

    const request = fetchMock.mock.calls[0][1] as RequestInit
    expect(JSON.parse(String(request.body))).toMatchObject({
      feedback: 'Condense to 1200 words.',
      source_revision_id: 'revision-3',
    })
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/adopt'))).toBe(false)
  })

  it('shows the newest backend candidate before the adopted chapter', () => {
    const documents = [
      { id: 'adopted-1', chapter_id: 'chapter-1', revision_number: 1, status: 'adopted', blocks: [] },
      { id: 'candidate-2', chapter_id: 'chapter-1', revision_number: 2, status: 'candidate', blocks: [] },
      { id: 'candidate-3', chapter_id: 'chapter-1', revision_number: 3, status: 'candidate', blocks: [] },
    ]

    expect(selectChapterDocument(documents, 'chapter-1')?.id).toBe('candidate-3')
    expect(selectChapterDocument(documents, 'chapter-2')).toBeUndefined()
  })

  it('does not resurface an older candidate after a newer revision is adopted', () => {
    const documents = [
      { id: 'candidate-4', chapter_id: 'chapter-1', revision_number: 4, status: 'candidate', blocks: [] },
      { id: 'adopted-5', chapter_id: 'chapter-1', revision_number: 5, status: 'adopted', blocks: [] },
    ]

    expect(selectChapterDocument(documents, 'chapter-1')?.id).toBe('adopted-5')
  })
})
