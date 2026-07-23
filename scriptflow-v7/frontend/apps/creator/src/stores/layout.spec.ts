import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useLayoutStore } from './layout'

describe('Creator immersive layout', () => {
  beforeEach(() => {
    window.localStorage.clear()
    setActivePinia(createPinia())
  })

  it('auto-hides only while Writer focus is active', () => {
    const layout = useLayoutStore()

    layout.enterWriter()
    expect(layout.writerFocus).toBe(true)
    expect(layout.sidebarHidden).toBe(true)

    layout.leaveWriter()
    expect(layout.writerFocus).toBe(false)
    expect(layout.sidebarHidden).toBe(false)
  })

  it('keeps an explicit hidden preference across focus changes', () => {
    const layout = useLayoutStore()

    layout.setManualHidden(true)
    layout.enterWriter()
    layout.leaveWriter()

    expect(layout.sidebarHidden).toBe(true)
    expect(window.localStorage.getItem('scriptflow-ui-sidebar-hidden')).toBe('1')
  })

  it('clamps and persists the resized sidebar width', () => {
    const layout = useLayoutStore()

    layout.setWidth(999)

    expect(layout.sidebarWidth).toBe(360)
    expect(window.localStorage.getItem('scriptflow-ui-sidebar-width')).toBe('360')
  })
})
