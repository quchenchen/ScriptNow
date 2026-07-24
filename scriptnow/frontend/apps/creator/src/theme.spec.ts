import { beforeEach, describe, expect, it, vi } from 'vitest'

describe('shared color theme', () => {
  beforeEach(() => {
    window.localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
    vi.resetModules()
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
  })

  it('persists an explicit theme and updates the document', async () => {
    const { useTheme } = await import('@scriptnow/shared')
    const theme = useTheme()
    theme.setTheme('dark')
    expect(theme.resolvedTheme.value).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(window.localStorage.getItem('scriptnow-ui-theme')).toBe('dark')
  })

  it('uses system preference until the user chooses explicitly', async () => {
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
    const { useTheme } = await import('@scriptnow/shared')
    const theme = useTheme()
    expect(theme.preference.value).toBe('system')
    expect(theme.resolvedTheme.value).toBe('dark')
  })
})
