// @vitest-environment jsdom

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import StoryCatalog from './StoryCatalog.vue'

const groups = [{
  id: 1,
  title: '第 1 卷',
  units: [
    { id: 11, title: '第 1 章 · 来信', status: 'adopted' },
    { id: 12, title: '第 2 章 · 追查', status: 'planned' },
  ],
}]

describe('StoryCatalog', () => {
  it('selects a unit and exposes creator-facing status', async () => {
    const wrapper = mount(StoryCatalog, {
      props: { groups, selectedUnitId: 11, busy: false, unitLabel: '章节' },
    })
    expect(wrapper.text()).toContain('待规划')
    const chapter = wrapper.get('button.tree')
    await chapter.trigger('click')
    expect(wrapper.emitted('select')?.[0]?.[0]).toEqual(groups[0].units[0])
  })

  it('supports keyboard-operable add and reorder without invalid moves', async () => {
    const wrapper = mount(StoryCatalog, {
      props: { groups, selectedUnitId: 11, busy: false, unitLabel: '章节' },
    })
    await wrapper.get('button[aria-label="在第 1 卷新增章节"]').trigger('click')
    expect(wrapper.emitted('add')?.[0]?.[0]).toEqual(groups[0])

    const moveFirstUp = wrapper.get('button[aria-label="上移第 1 章 · 来信"]')
    expect(moveFirstUp.attributes('disabled')).toBeDefined()
    const moveSecondUp = wrapper.get('button[aria-label="上移第 2 章 · 追查"]')
    await moveSecondUp.trigger('click')
    expect(wrapper.emitted('move')?.[0]).toEqual([groups[0], groups[0].units[1], -1])
  })

  it('uses scene terminology when the workspace is a script', () => {
    const scriptGroups = [{ id: 2, title: '第 1 集', units: [{ id: 21, title: 'Scene 1 · 相遇', status: 'planned' }] }]
    const wrapper = mount(StoryCatalog, { props: { groups: scriptGroups, selectedUnitId: 21, busy: false, unitLabel: '场次' } })
    expect(wrapper.get('button[aria-label="在第 1 集新增场次"]').attributes('aria-label')).toBe('在第 1 集新增场次')
  })
})
