// @vitest-environment jsdom

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ManuscriptEditor from './ManuscriptEditor.vue'

const base = {
  unit_type: 'chapter' as const, ordinal: 2, title: '第二章 · 追查', adopted_content: '正式正文',
  candidate: { content: '候选正文', state_delta: {}, thread_actions: [], continuity_report: [] },
}

describe('ManuscriptEditor', () => {
  it('keeps a candidate separate until the creator adopts it', async () => {
    const wrapper = mount(ManuscriptEditor, { props: { manuscript: { ...base, status: 'candidate_ready' }, novel: true, busy: false, documentContent: '', metadata: {}, saveStatus: 'idle' } })
    expect(wrapper.text()).toContain('候选正文 · 尚未写入作品')
    expect(wrapper.text()).toContain('候选正文')
    await wrapper.get('button.primary').trigger('click')
    expect(wrapper.emitted('adopt')).toHaveLength(1)
  })

  it('renders adopted content as a selectable editor surface', async () => {
    const wrapper = mount(ManuscriptEditor, { props: { manuscript: { ...base, status: 'adopted' }, novel: true, busy: false, documentContent: '正式正文', metadata: { pov_character: '二丫', narrative_person: '第三人称', time_position: '当夜' }, saveStatus: 'saved' } })
    const editor = wrapper.get('textarea[aria-label="已采用章节正文"]')
    expect((editor.element as HTMLTextAreaElement).value).toBe('正式正文')
    await editor.trigger('select')
    expect(wrapper.emitted('selectText')).toHaveLength(1)
    await editor.setValue('创作者修改后的正文')
    expect(wrapper.emitted('updateDocument')?.at(-1)?.[0]).toBe('创作者修改后的正文')
    expect(wrapper.text()).toContain('已保存')
    await wrapper.get('input[placeholder="本章跟随谁"]').setValue('核心行动者')
    expect(wrapper.emitted('updateMetadata')?.at(-1)?.[0]).toMatchObject({ pov_character: '核心行动者', narrative_person: '第三人称' })
  })

  it('uses scene terminology for script manuscripts', () => {
    const wrapper = mount(ManuscriptEditor, { props: { manuscript: { ...base, unit_type: 'scene', status: 'adopted' }, novel: false, busy: false, documentContent: '正式正文', metadata: { scene_heading: '内景', location: '门厅', time_of_day: '清晨', characters: ['二丫'] }, saveStatus: 'idle' } })
    expect(wrapper.get('textarea').attributes('aria-label')).toBe('已采用场次正文')
    expect(wrapper.text()).toContain('生成第 3 场候选')
  })

  it('offers history restoration without mutating content locally', async () => {
    const wrapper = mount(ManuscriptEditor, { props: {
      manuscript: { ...base, status: 'adopted' }, novel: true, busy: false,
      documentContent: '第二版', metadata: {}, saveStatus: 'saved', currentVersion: 2,
      versions: [{ version: 2, content: '第二版', source: 'manual_edit', metadata: {} }, { version: 1, content: '第一版', source: 'adopted_baseline', metadata: {} }],
    } })
    const restore = wrapper.get('button:not([disabled])')
    await restore.trigger('click')
    expect(wrapper.emitted('restoreVersion')?.[0]?.[0]).toBe(1)
  })
})
