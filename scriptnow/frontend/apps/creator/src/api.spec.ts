import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from './api'

describe('creator API client', () => {
  beforeEach(() => {
    vi.stubGlobal('document', { cookie: 'sf_csrf=test-csrf; path=/' })
  })
  afterEach(() => vi.unstubAllGlobals())

  it('adds CSRF to mutations and keeps browser credentials', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: 'project-1' }), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await api('/projects', { method: 'POST', body: JSON.stringify({ name: 'Story' }) })

    expect(fetchMock).toHaveBeenCalledOnce()
    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(path).toBe('/api/projects')
    expect(init.credentials).toBe('include')
    expect(new Headers(init.headers).get('X-CSRF-Token')).toBe('test-csrf')
  })

  it('refreshes once after a 401 and retries the original request', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response('', { status: 401 }))
      .mockResolvedValueOnce(new Response('{}', { status: 200 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify([{ id: 'project-1' }]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    vi.stubGlobal('fetch', fetchMock)

    const projects = await api<Array<{ id: string }>>('/projects')

    expect(projects[0].id).toBe('project-1')
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      '/api/projects',
      '/api/auth/refresh',
      '/api/projects',
    ])
  })

  it('shares one refresh request across concurrent unauthorized calls', async () => {
    let releaseRefresh!: () => void
    const refreshGate = new Promise<void>((resolve) => { releaseRefresh = resolve })
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      const path = String(input)
      if (path === '/api/auth/refresh') {
        await refreshGate
        return new Response('{}', { status: 200 })
      }
      const attempts = fetchMock.mock.calls.filter((call) => String(call[0]) === path).length
      return attempts === 1
        ? new Response('', { status: 401 })
        : new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } })
    })
    vi.stubGlobal('fetch', fetchMock)

    const requests = Promise.all([api('/projects'), api('/projects/project-1')])
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))
    releaseRefresh()
    await requests

    expect(fetchMock.mock.calls.filter((call) => call[0] === '/api/auth/refresh')).toHaveLength(1)
  })

  it('returns a typed status error for quota handling', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: 'insufficient token balance' }), {
          status: 402,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )

    await expect(api('/runs', { method: 'POST' })).rejects.toEqual(
      expect.objectContaining({ status: 402, message: 'insufficient token balance' }),
    )
  })
})
