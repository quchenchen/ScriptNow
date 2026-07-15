import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

// Auth
export const login = (phone: string) => api.post('/auth/login', { phone })
export const getUser = (userId: number) => api.get('/auth/user', { params: { user_id: userId } })

// Projects
export const listProjects = (userId: number) => api.get('/projects/list', { params: { user_id: userId } })
export const createProject = (data: any) => api.post('/projects/create', data)
export const getProject = (id: number) => api.get(`/projects/${id}`)
export const deleteProject = (id: number) => api.delete(`/projects/${id}`)
export const updateProjectSettings = (id: number, data: object) => api.put(`/projects/${id}/settings`, data)
export const updateStage = (id: number, stage: string) => api.put(`/projects/${id}/stage`, null, { params: { stage } })

// Workspace
export const listEpisodes = (projectId: number, status?: string) =>
  api.get(`/workspace/${projectId}/episodes`, { params: status ? { status } : {} })
export const getEpisode = (projectId: number, epNumber: number) =>
  api.get(`/workspace/${projectId}/episodes/${epNumber}`)
export const updateEpisode = (projectId: number, epNumber: number, data: any) =>
  api.put(`/workspace/${projectId}/episodes/${epNumber}`, data)

// Agent Chat (SSE)
export const agentChat = (projectId: number, message: string, model: string, onData: (data: any) => void) => {
  const controller = new AbortController()
  fetch(`/api/workspace/${projectId}/agent/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, model }),
    signal: controller.signal,
  }).then(async (res) => {
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
          try { onData(JSON.parse(line.slice(6))) } catch {}
        }
      }
    }
  })
  return controller
}
