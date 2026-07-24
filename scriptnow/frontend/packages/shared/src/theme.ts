import { computed, ref } from 'vue'

export type ThemePreference = 'system' | 'light' | 'dark'
export type ResolvedTheme = 'light' | 'dark'

const STORAGE_KEY = 'scriptnow-ui-theme'
const LEGACY_STORAGE_KEY = 'scriptflow-ui-theme'
const DARK_QUERY = '(prefers-color-scheme: dark)'

function storedPreference(): ThemePreference {
  if (typeof window === 'undefined') return 'system'
  const value = window.localStorage.getItem(STORAGE_KEY)
    ?? window.localStorage.getItem(LEGACY_STORAGE_KEY)
  if (value === 'light' || value === 'dark') {
    window.localStorage.setItem(STORAGE_KEY, value)
    window.localStorage.removeItem(LEGACY_STORAGE_KEY)
  }
  return value === 'light' || value === 'dark' ? value : 'system'
}

function systemTheme(): ResolvedTheme {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia(DARK_QUERY).matches
    ? 'dark'
    : 'light'
}

const preference = ref<ThemePreference>(storedPreference())
const resolvedTheme = ref<ResolvedTheme>(preference.value === 'system' ? systemTheme() : preference.value)

function applyTheme(value: ThemePreference, persist = true) {
  preference.value = value
  resolvedTheme.value = value === 'system' ? systemTheme() : value
  if (typeof document !== 'undefined') {
    document.documentElement.dataset.theme = resolvedTheme.value
    document.documentElement.style.colorScheme = resolvedTheme.value
  }
  if (persist && typeof window !== 'undefined') {
    if (value === 'system') window.localStorage.removeItem(STORAGE_KEY)
    else window.localStorage.setItem(STORAGE_KEY, value)
  }
}

applyTheme(preference.value, false)

if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
  const media = window.matchMedia(DARK_QUERY)
  media.addEventListener('change', () => {
    if (preference.value === 'system') applyTheme('system', false)
  })
  window.addEventListener('storage', (event) => {
    if (event.key !== STORAGE_KEY) return
    const value = event.newValue === 'light' || event.newValue === 'dark' ? event.newValue : 'system'
    applyTheme(value, false)
  })
}

export function useTheme() {
  return {
    preference: computed(() => preference.value),
    resolvedTheme: computed(() => resolvedTheme.value),
    setTheme: applyTheme,
    toggleTheme: () => applyTheme(resolvedTheme.value === 'dark' ? 'light' : 'dark'),
  }
}
