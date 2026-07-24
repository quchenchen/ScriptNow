import { flushPromises, mount } from '@vue/test-utils'
import axe from 'axe-core'
import { afterEach, describe, expect, it, vi } from 'vitest'

import App from './App.vue'

describe('Admin accessibility gate', () => {
  afterEach(() => vi.restoreAllMocks())

  it('has no serious or critical axe violations on the login surface', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 401 })))
    const wrapper = mount(App, { attachTo: document.body })
    await flushPromises()
    const results = await axe.run(wrapper.element, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] },
    })
    expect(results.violations.filter((item) => ['serious', 'critical'].includes(item.impact ?? ''))).toEqual([])
    wrapper.unmount()
  })
})
