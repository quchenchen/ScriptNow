export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message)
  }
}

let refreshRequest: Promise<boolean> | undefined
let authExpiredNotified = false

function cookie(name: string): string | undefined {
  return document.cookie
    .split('; ')
    .find((item) => item.startsWith(`${name}=`))
    ?.split('=')
    .slice(1)
    .join('=')
}

async function parseError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string }
    return body.detail ?? `请求失败（${response.status}）`
  } catch {
    return `请求失败（${response.status}）`
  }
}

async function refreshSession(): Promise<boolean> {
  if (refreshRequest) return refreshRequest
  const csrf = cookie('sf_csrf')
  if (!csrf) return false
  refreshRequest = fetch('/api/auth/refresh', {
    method: 'POST',
    credentials: 'include',
    headers: { 'X-CSRF-Token': decodeURIComponent(csrf) },
  }).then((response) => response.ok).finally(() => {
    refreshRequest = undefined
  })
  return refreshRequest
}

function notifyAuthExpired() {
  if (authExpiredNotified || window.location.pathname === '/login') return
  authExpiredNotified = true
  window.dispatchEvent(new CustomEvent('scriptflow:auth-expired'))
}

export async function api<T>(
  path: string,
  init: RequestInit = {},
  allowRefresh = true,
): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (init.method && !['GET', 'HEAD'].includes(init.method.toUpperCase())) {
    const csrf = cookie('sf_csrf')
    if (csrf) headers.set('X-CSRF-Token', decodeURIComponent(csrf))
  }
  const response = await fetch(`/api${path}`, { ...init, headers, credentials: 'include' })
  if (response.status === 401 && allowRefresh && path !== '/auth/refresh') {
    const refreshed = await refreshSession()
    if (refreshed) {
      authExpiredNotified = false
      return api<T>(path, init, false)
    }
    notifyAuthExpired()
  }
  if (!response.ok) throw new ApiError(response.status, await parseError(response))
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
