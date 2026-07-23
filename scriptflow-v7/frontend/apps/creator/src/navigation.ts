export function safeNextPath(value: unknown): string {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//')) return '/'
  let target: URL
  try { target = new URL(value, window.location.origin) }
  catch { return '/' }
  if (target.origin !== window.location.origin) return '/'
  if (['/', '/welcome', '/new', '/account'].includes(target.pathname)) return target.pathname
  if (/^\/projects\/[A-Za-z0-9-]{1,64}$/.test(target.pathname)) return target.pathname
  if (/^\/projects\/[A-Za-z0-9-]{1,64}\/agents$/.test(target.pathname)) return target.pathname
  return '/'
}
