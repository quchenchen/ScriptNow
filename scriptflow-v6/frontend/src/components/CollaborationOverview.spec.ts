// @vitest-environment jsdom

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import CollaborationOverview from './CollaborationOverview.vue'

describe('CollaborationOverview', () => {
  it('explains candidate state and handoff in creator language', () => {
    const wrapper = mount(CollaborationOverview, { props: {
      unitIntent: '迫使主角承认自己隐瞒了信件',
      unitState: 'candidate',
      agentHeadline: '等待你判断正文候选',
      agentDetail: '候选尚未写入正式正文',
      pendingCount: 1,
      handoff: { characters: 2, relationships: 1, openThreads: 3, previousTitle: '旧信', warnings: [] },
    } })
    expect(wrapper.text()).toContain('已有正文候选，尚未成为作品事实')
    expect(wrapper.text()).toContain('1 项内容不会自动写入作品')
    expect(wrapper.text()).toContain('2 个角色状态 · 1 条关系 · 3 条未完剧情')
  })

  it('routes explicit creator actions to the parent workspace', async () => {
    const wrapper = mount(CollaborationOverview, { props: {
      unitIntent: '', unitState: 'planned', agentHeadline: '等待下一步', agentDetail: '', pendingCount: 0, handoff: null,
    } })
    await wrapper.get('button.actionable').trigger('click')
    await wrapper.get('button.rail-directive-shortcut').trigger('click')
    expect(wrapper.emitted('openDecisions')).toHaveLength(1)
    expect(wrapper.emitted('openDirectives')).toHaveLength(1)
  })
})
