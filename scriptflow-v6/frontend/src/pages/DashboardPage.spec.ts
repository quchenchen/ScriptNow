// @vitest-environment jsdom

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import DashboardPage from './DashboardPage.vue'

describe('DashboardPage', () => {
  it('shows resumable creator work and emits the selected project', async () => {
    const project = { id: 10, title: '雾港来信', goal_type: 'original-script', goal_label: '创作一个剧本', pulse: { state: 'waiting_user', needs_user: true, headline: '第 8 场等待判断' } }
    const wrapper = mount(DashboardPage, { props: { projects: [project] } })
    expect(wrapper.text()).toContain('1 项等待判断')
    await wrapper.get('button.project').trigger('click')
    expect(wrapper.emitted('open')?.[0]?.[0]).toEqual(project)
  })
})
