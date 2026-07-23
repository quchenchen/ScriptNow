import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import NovelStoryMapEditor from './NovelStoryMapEditor.vue'
import ScriptStoryMapEditor from './ScriptStoryMapEditor.vue'

describe('domain StoryMap editors', () => {
  it('creates a Script structure candidate payload without mutating the adopted source', async () => {
    const episodes = [{ id: 'episode-1', ordinal: 1, title: '第一集', scenes: [{
      id: 'scene-1', ordinal: 1, title: '触发事件', duration_seconds_target: 120,
      beats: [{ id: 'beat-1', objective: '触发选择', anchor_ids: ['character:protagonist'] }],
    }] }]
    const wrapper = mount(ScriptStoryMapEditor, { props: { episodes } })
    await wrapper.findAll('button').find((item) => item.text().includes('添加场景'))!.trigger('click')
    await wrapper.findAll('button').find((item) => item.text().includes('保存为结构候选'))!.trigger('click')
    const payload = wrapper.emitted('save')![0][0] as typeof episodes
    expect(payload[0].scenes).toHaveLength(2)
    expect(episodes[0].scenes).toHaveLength(1)
  })

  it('keeps Novel chapter fields independent from Script scene fields', async () => {
    const volumes = [{ id: 'volume-1', ordinal: 1, title: '第一卷', chapters: [{
      id: 'chapter-1', ordinal: 1, title: '第一章', target_words: 3000,
      point_of_view: '第三人称限知', beats: [],
    }] }]
    const wrapper = mount(NovelStoryMapEditor, { props: { volumes } })
    await wrapper.findAll('button').find((item) => item.text().includes('添加章节'))!.trigger('click')
    await wrapper.findAll('button').find((item) => item.text().includes('保存为结构候选'))!.trigger('click')
    const payload = wrapper.emitted('save')![0][0] as typeof volumes
    expect(payload[0].chapters).toHaveLength(2)
    expect(payload[0].chapters[1]).toHaveProperty('target_words', 3000)
    expect(payload[0].chapters[1]).not.toHaveProperty('duration_seconds_target')
  })
})
