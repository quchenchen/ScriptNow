import { defineStore } from 'pinia'

const HIDDEN_KEY = 'scriptnow-ui-sidebar-hidden'
const WIDTH_KEY = 'scriptnow-ui-sidebar-width'
const SIDECAR_HIDDEN_KEY = 'scriptnow-ui-writer-sidecar-hidden'
const LEGACY_PREFIX = 'scriptflow-ui-'
export type StudioView = 'ideation' | 'blueprint' | 'graph' | 'storymap' | 'writer'

function storedBoolean(key: string): boolean {
  if (typeof window === 'undefined') return false
  const legacyKey = key.replace('scriptnow-ui-', LEGACY_PREFIX)
  const value = window.localStorage.getItem(key) ?? window.localStorage.getItem(legacyKey)
  if (value !== null && !window.localStorage.getItem(key)) {
    window.localStorage.setItem(key, value)
    window.localStorage.removeItem(legacyKey)
  }
  return value === '1'
}

function storedWidth(): number {
  if (typeof window === 'undefined') return 240
  const legacyKey = WIDTH_KEY.replace('scriptnow-ui-', LEGACY_PREFIX)
  const stored = window.localStorage.getItem(WIDTH_KEY) ?? window.localStorage.getItem(legacyKey)
  if (stored !== null && !window.localStorage.getItem(WIDTH_KEY)) {
    window.localStorage.setItem(WIDTH_KEY, stored)
    window.localStorage.removeItem(legacyKey)
  }
  const value = Number(stored)
  return Number.isFinite(value) && value >= 180 && value <= 360 ? value : 240
}

export const useLayoutStore = defineStore('creator-layout', {
  state: () => ({
    manualHidden: storedBoolean(HIDDEN_KEY),
    autoHidden: false,
    writerFocus: false,
    sidebarWidth: storedWidth(),
    writerSidecarHidden: storedBoolean(SIDECAR_HIDDEN_KEY),
    mobileOpen: false,
    studioView: 'ideation' as StudioView,
  }),
  getters: {
    sidebarHidden: (state) => state.manualHidden || state.autoHidden,
  },
  actions: {
    setManualHidden(hidden: boolean) {
      this.manualHidden = hidden
      this.autoHidden = false
      window.localStorage.setItem(HIDDEN_KEY, hidden ? '1' : '0')
    },
    toggleSidebar() { this.setManualHidden(!this.sidebarHidden) },
    setWidth(width: number) {
      this.sidebarWidth = Math.max(180, Math.min(360, Math.round(width)))
      window.localStorage.setItem(WIDTH_KEY, String(this.sidebarWidth))
    },
    setWriterSidecarHidden(hidden: boolean) {
      this.writerSidecarHidden = hidden
      window.localStorage.setItem(SIDECAR_HIDDEN_KEY, hidden ? '1' : '0')
    },
    toggleWriterSidecar() { this.setWriterSidecarHidden(!this.writerSidecarHidden) },
    enterWriter() {
      this.writerFocus = true
      if (!this.manualHidden) this.autoHidden = true
    },
    leaveWriter() {
      this.writerFocus = false
      this.autoHidden = false
    },
    setStudioView(view: StudioView) {
      this.studioView = view
      this.mobileOpen = false
      if (view === 'writer') this.enterWriter()
      else this.leaveWriter()
    },
  },
})
