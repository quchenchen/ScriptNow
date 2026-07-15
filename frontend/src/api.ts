import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

// ── Auth interceptor ──────────────────────────────────────────
// Read token from the persisted login response and attach it as Bearer
// to every request. On 401, drop the session and reload to LoginPage.
//
// We install on BOTH the ``api`` instance AND the global ``axios`` default —
// several places (e.g. composables/useWorkspace.ts) call ``axios.get('/api/...')``
// directly. Installing on both keeps the auth flow unified without forcing
// a large refactor.

function readToken(): string | null {
  try {
    const raw = localStorage.getItem('scriptflow_user')
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return typeof parsed?.token === 'string' ? parsed.token : null
  } catch {
    return null
  }
}

function attachAuthInterceptors(instance: typeof axios | typeof api) {
  instance.interceptors.request.use((config) => {
    const token = readToken()
    if (token) {
      config.headers = config.headers ?? {}
      config.headers['Authorization'] = `Bearer ${token}`
    }
    return config
  })

  instance.interceptors.response.use(
    (r) => r,
    (err) => {
      if (err?.response?.status === 401) {
        localStorage.removeItem('scriptflow_user')
        if (typeof window !== 'undefined') window.location.reload()
      }
      return Promise.reject(err)
    },
  )
}

attachAuthInterceptors(api)
attachAuthInterceptors(axios)

// ── Auth API ──────────────────────────────────────────────────
// Login/register live on this shared axios so the token interceptor picks up
// any browser-set token; register/login themselves don't need auth.
export const login = (username: string, password: string) =>
  api.post('/auth/login', { username, password })
export const register = (username: string, password: string) =>
  api.post('/auth/register', { username, password })

// ── Projects ──────────────────────────────────────────────────
// user_id is derived server-side from the JWT — never sent from client.
export const listProjects = () => api.get('/projects/list')
export const createProject = (data: any) => api.post('/projects/create', data)
export const getProject = (id: number) => api.get(`/projects/${id}`)
export const deleteProject = (id: number) => api.delete(`/projects/${id}`)
export const updateProjectSettings = (id: number, data: object) =>
  api.put(`/projects/${id}/settings`, data)
export const updateStage = (id: number, stage: string) =>
  api.put(`/projects/${id}/stage`, null, { params: { stage } })
export const listPipelines = () => api.get('/projects/pipelines')

// ── Source documents (adaption/rewrite RAG) ───────────────────
export const listSources = (projectId: number) => api.get(`/projects/${projectId}/sources`)
export const getSource = (projectId: number, sourceId: number) =>
  api.get(`/projects/${projectId}/sources/${sourceId}`)
export const deleteSource = (projectId: number, sourceId: number) =>
  api.delete(`/projects/${projectId}/sources/${sourceId}`)
export const searchSources = (projectId: number, q: string, k = 5) =>
  api.get(`/projects/${projectId}/sources-search`, { params: { q, k } })
export const expandChunk = (projectId: number, chunkId: number, ctx = 0) =>
  api.get(`/projects/${projectId}/chunks/${chunkId}`, { params: { ctx } })

/**
 * Upload one source document. ``kind`` is informational for now (future
 * filtering); ``onProgress`` fires with 0-100 as axios reports xhr progress.
 */
export const uploadSource = (
  projectId: number,
  file: File,
  kind: string = 'adaptation',
  onProgress?: (pct: number) => void,
) => {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('kind', kind)
  return api.post(`/projects/${projectId}/sources/upload`, fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e) => {
      if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100))
    },
  })
}


// ── Workspace ─────────────────────────────────────────────────
export const listEpisodes = (projectId: number, status?: string) =>
  api.get(`/workspace/${projectId}/episodes`, { params: status ? { status } : {} })
export const getEpisode = (projectId: number, epNumber: number) =>
  api.get(`/workspace/${projectId}/episodes/${epNumber}`)
export const updateEpisode = (projectId: number, epNumber: number, data: any) =>
  api.put(`/workspace/${projectId}/episodes/${epNumber}`, data)
export const getChat = (projectId: number) => api.get(`/workspace/${projectId}/chat`)
export const saveChat = (projectId: number, data: any) =>
  api.post(`/workspace/${projectId}/chat`, data)

// ── Memory ────────────────────────────────────────────────────
export const listCharacters = (projectId: number) => api.get(`/memory/${projectId}/characters`)
export const listForeshadows = (projectId: number, status = '') =>
  api.get(`/memory/${projectId}/foreshadows`, { params: status ? { status } : {} })
export const getMemory = (projectId: number) => api.get(`/memory/${projectId}/memory`)

// ── Agent Chat (SSE) ──────────────────────────────────────────
// fetch() doesn't go through axios; we attach the Bearer header manually.
export const agentChat = (
  projectId: number,
  message: string,
  model: string,
  onData: (data: any) => void,
) => {
  const controller = new AbortController()
  const token = readToken()
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`

  fetch(`/api/workspace/${projectId}/agent/chat`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ message, model }),
    signal: controller.signal,
  }).then(async (res) => {
    if (res.status === 401) {
      localStorage.removeItem('scriptflow_user')
      if (typeof window !== 'undefined') window.location.reload()
      return
    }
    const reader = res.body?.getReader()
    if (!reader) return
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            onData(JSON.parse(line.slice(6)))
          } catch {
            /* ignore malformed SSE frames */
          }
        }
      }
    }
  })
  return controller
}
