import { defineStore } from 'pinia'

const HIDDEN_KEY = 'scriptflow-ui-sidebar-hidden'
const WIDTH_KEY = 'scriptflow-ui-sidebar-width'
const SIDECAR_HIDDEN_KEY = 'scriptflow-ui-writer-sidecar-hidden'
export type StudioView = 'ideation' | 'blueprint' | 'graph' | 'storymap' | 'writer'

function storedBoolean(key: string): boolean {
  return typeof window !== 'undefined' && window.localStorage.getItem(key) === '1'
}

function storedWidth(): number {
  if (typeof window === 'undefined') return 240
  const value = Number(window.localStorage.getItem(WIDTH_KEY))
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
