import { describe, expect, it } from 'vitest'

import { parseAgentMessage } from './agentMessage'

describe('AgentMessage', () => {
  it('turns markdown-like model output into readable blocks without markup tokens', () => {
    const blocks = parseAgentMessage([
      '## 项目诊断',
      '**项目**：电光美人 | **状态**：`ready_with_risks`',
      '---',
      '## 需要确认',
      '1. 类型 / Genre',
      '2. 时长 / 格式',
    ].join('\n'))

    expect(blocks).toEqual([
      { type: 'heading', level: 2, text: '项目诊断' },
      { type: 'paragraph', text: '项目：电光美人 | 状态：ready_with_risks' },
      { type: 'divider' },
      { type: 'heading', level: 2, text: '需要确认' },
      { type: 'list', ordered: true, items: ['类型 / Genre', '时长 / 格式'] },
    ])
  })

  it('preserves the list semantics emitted by the Agent instead of inventing numbering', () => {
    const blocks = parseAgentMessage([
      '1. **类型 / Genre**：科幻',
      '2. **时长 / 格式**：电影长片',
      '- **A**：人物驱动',
      '- **B**：概念驱动',
    ].join('\n'))

    expect(blocks).toEqual([
      { type: 'list', ordered: true, items: ['类型 / Genre：科幻', '时长 / 格式：电影长片'] },
      { type: 'list', ordered: false, items: ['A：人物驱动', 'B：概念驱动'] },
    ])
  })

  it('keeps letter-labelled choices as bullets with their original labels', () => {
    expect(parseAgentMessage('**A**：人物驱动\n**B**：概念驱动')).toEqual([
      { type: 'list', ordered: false, items: ['A：人物驱动', 'B：概念驱动'] },
    ])
  })

  it('parses markdown tables into structured rows', () => {
    expect(parseAgentMessage([
      '| 要素 | 评估 | 说明 |',
      '|------|------|------|',
      '| 场景集中度 | 高 | 场景可控 |',
      '| 特效需求 | 中等 | 石膏碎裂与幽灵视觉 |',
      '',
      '后续建议。',
    ].join('\n'))).toEqual([
      {
        type: 'table',
        headers: ['要素', '评估', '说明'],
        rows: [
          ['场景集中度', '高', '场景可控'],
          ['特效需求', '中等', '石膏碎裂与幽灵视觉'],
        ],
      },
      { type: 'paragraph', text: '后续建议。' },
    ])
  })

  it('recovers tables collapsed by streaming or provider formatting', () => {
    expect(parseAgentMessage(
      '| 要素 | 评估 | 说明 | |------|------|------| | 场景集中度 | 高 | 场景可控 | | 特效需求 | 中等 | 石膏碎裂与幽灵视觉 |',
    )).toEqual([
      {
        type: 'table',
        headers: ['要素', '评估', '说明'],
        rows: [
          ['场景集中度', '高', '场景可控'],
          ['特效需求', '中等', '石膏碎裂与幽灵视觉'],
        ],
      },
    ])
  })

  it('renders quotes and code as semantic blocks', () => {
    expect(parseAgentMessage('> 原文证据\n\n```text\nscene 1\n```')).toEqual([
      { type: 'quote', text: '原文证据' },
      { type: 'code', text: 'scene 1' },
    ])
  })
})
