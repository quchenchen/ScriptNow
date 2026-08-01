import { describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import {
  appendUniqueStream,
  deriveReviewCheckpoint,
  eventBody,
  isDockVisibleStreamBlock,
  isFocusEvent,
  isReviewVisibleStreamBlock,
  parseSse,
  useDockStore,
} from './dock'

describe('Agent Dock SSE projection', () => {
  it('preserves ordered Thinking, Tool, Data and Text blocks with cursors', () => {
    const blocks = parseSse([
      'id: 1\nevent: system\ndata: {"block":"thinking","phase":"delta","delta":"分析"}',
      'id: 2\nevent: node\ndata: {"block":"tool","phase":"end","title":"读取上下文"}',
      'id: 3\nevent: node\ndata: {"block":"data","phase":"end","title":"上下文包"}',
      'id: 4\nevent: conversation\ndata: {"block":"text","phase":"delta","delta":"建议"}',
      '',
    ].join('\n\n'))

    expect(blocks.map((block) => [block.id, block.block, block.text ?? block.title])).toEqual([
      ['1', 'thinking', '分析'], ['2', 'tool', '读取上下文'],
      ['3', 'data', '上下文包'], ['4', 'text', '建议'],
    ])
  })

  it('projects a completed reply as one readable message', () => {
    const blocks = parseSse(
      'id: 9\nevent: conversation\ndata: {"block":"text","phase":"end","title":"Agent 评审结果","content":"完整评审正文"}\n\n',
    )

    expect(blocks).toHaveLength(1)
    expect(blocks[0]).toMatchObject({
      id: '9',
      block: 'text',
      phase: 'end',
      title: 'Agent 评审结果',
      text: '完整评审正文',
    })
  })

  it('drops replayed blocks after reconnect without disturbing order', () => {
    const existing = parseSse('id: 1\nevent: system\ndata: {"block":"thinking","delta":"分析"}\n\n')
    const replay = parseSse([
      'id: 1\nevent: system\ndata: {"block":"thinking","delta":"分析"}',
      'id: 2\nevent: conversation\ndata: {"block":"text","delta":"完成"}',
      '',
    ].join('\n\n'))

    expect(appendUniqueStream(existing, replay).map((block) => block.id)).toEqual(['1', '2'])
  })

  it('collapses repeated runtime status cards while keeping the newest cursor', () => {
    const heartbeats = parseSse([
      'id: 5\nevent: heartbeat\ndata: {"block":"system","phase":"delta","title":"主笔仍在创作，候选稿将在校验完成后解锁"}',
      'id: 8\nevent: heartbeat\ndata: {"block":"system","phase":"delta","title":"主笔仍在创作，候选稿将在校验完成后解锁"}',
      'id: 13\nevent: heartbeat\ndata: {"block":"system","phase":"delta","title":"主笔仍在创作，候选稿将在校验完成后解锁"}',
      '',
    ].join('\n\n'))

    const result = appendUniqueStream([], heartbeats)
    expect(result).toHaveLength(1)
    expect(result[0]?.id).toBe('13')
  })

  it('coalesces streaming deltas into one growing block', () => {
    const deltas = parseSse([
      'id: 20\nevent: conversation\ndata: {"block":"text","phase":"delta","title":"章节候选稿只读预览","delta":"The silver "}',
      'id: 21\nevent: conversation\ndata: {"block":"text","phase":"delta","title":"章节候选稿只读预览","delta":"leaf remembers."}',
      '',
    ].join('\n\n'))

    const result = appendUniqueStream([], deltas)
    expect(result).toHaveLength(1)
    expect(result[0]).toMatchObject({ id: '21', text: 'The silver leaf remembers.' })
  })

  it('coalesces legacy planning tokens and hides them from the review conversation', () => {
    const fragments = parseSse([
      'id: 30\nevent: system\ndata: {"block":"thinking","phase":"planning","title":"Agent 分析过程","delta":"Reading "}',
      'id: 31\nevent: system\ndata: {"block":"thinking","phase":"planning","title":"Agent 分析过程","delta":"relevant "}',
      'id: 32\nevent: system\ndata: {"block":"thinking","phase":"planning","title":"Agent 分析过程","delta":"skills"}',
      '',
    ].join('\n\n'))

    const result = appendUniqueStream([], fragments)
    expect(result).toHaveLength(1)
    expect(result[0]?.text).toBe('Reading relevant skills')
    expect(isReviewVisibleStreamBlock(result[0]!)).toBe(false)
  })

  it('shows only completed user-readable review briefs', () => {
    expect(isReviewVisibleStreamBlock({
      id: '40',
      type: 'system',
      block: 'thinking',
      phase: 'end',
      title: '评审框架',
      text: '先核查人物目标，再按场景定位证据。',
    })).toBe(true)
  })

  it('keeps the newest cursor last when status events interleave manuscript deltas', () => {
    const blocks = parseSse([
      'id: 20\nevent: conversation\ndata: {"block":"text","phase":"delta","title":"章节候选稿只读预览","delta":"The silver "}',
      'id: 21\nevent: heartbeat\ndata: {"block":"system","phase":"delta","title":"主笔仍在创作，候选稿将在校验完成后解锁"}',
      'id: 22\nevent: conversation\ndata: {"block":"text","phase":"delta","title":"章节候选稿只读预览","delta":"leaf remembers."}',
      '',
    ].join('\n\n'))

    const result = appendUniqueStream([], blocks)
    expect(result.at(-1)).toMatchObject({ id: '22', text: 'The silver leaf remembers.' })
  })

  it('keeps manuscript delivery in the editor instead of duplicating it in the Dock', () => {
    expect(isDockVisibleStreamBlock({
      id: '1', type: 'conversation', block: 'text', phase: 'delta',
      title: '章节候选稿只读预览', text: '{"blocks":[]}',
    })).toBe(false)
    expect(isDockVisibleStreamBlock({
      id: '2', type: 'conversation', block: 'thinking', phase: 'delta',
      title: '主笔的创作思路', text: '先承接上一章。',
    })).toBe(true)
  })
})

describe('Agent Dock information hierarchy', () => {
  it('keeps the reviewer open while the studio refreshes its creative role', () => {
    setActivePinia(createPinia())
    const dock = useDockStore()
    dock.setCreativeRole('architect')
    dock.openReviewer()
    dock.setCreativeRole('writer')

    expect(dock.role).toBe('reviewer')
    dock.returnToCreativeRole()
    expect(dock.role).toBe('writer')
  })

  it('derives the latest unadopted decision checkpoint from project events', () => {
    const events = [
      {
        id: '1', type: 'node' as const, title: '候选', payload: { action: 'novel_story_core.propose' },
        occurred_at: '', count: 1,
      },
      {
        id: '2', type: 'decision' as const, title: '采纳', payload: { action: 'novel_story_core.adopt' },
        occurred_at: '', count: 1,
      },
      {
        id: '3', type: 'node' as const, title: '章节候选', payload: {
          action: 'novel_document.revise',
          chapter_id: 'chapter-4',
        },
        occurred_at: '', count: 1,
      },
    ]

    expect(deriveReviewCheckpoint(events)).toEqual({
      key: 'document:3',
      label: '正文候选决策',
      action: 'novel_document.revise',
      focus: { medium: 'novel', unit_id: 'chapter-4' },
    })
  })

  it('clears a checkpoint after the corresponding artifact is adopted', () => {
    const events = [
      {
        id: '1', type: 'node' as const, title: '蓝图候选', payload: { action: 'script_blueprint.propose' },
        occurred_at: '', count: 1,
      },
      {
        id: '2', type: 'decision' as const, title: '采纳蓝图', payload: { action: 'script_blueprint.adopt' },
        occurred_at: '', count: 1,
      },
    ]

    expect(deriveReviewCheckpoint(events)).toBeUndefined()
  })

  it('keeps conversations, decisions and failures in the default focus view', () => {
    const event = (type: 'chat' | 'node' | 'decision' | 'system', status?: string) => ({
      id: type, type, title: type, payload: status ? { status } : {}, occurred_at: '', count: 1,
    })

    expect(isFocusEvent(event('chat'))).toBe(true)
    expect(isFocusEvent(event('decision'))).toBe(true)
    expect(isFocusEvent(event('node'))).toBe(false)
    expect(isFocusEvent(event('system'))).toBe(false)
    expect(isFocusEvent(event('system', 'failed'))).toBe(true)
  })

  it('does not repeat a short message as both title and body', () => {
    expect(eventBody('重新做创意发散', '重新做创意发散')).toBeUndefined()
    expect(eventBody('重新做创意发散', '重新做创意发散，并保留当前世界规则。')).toContain('保留当前世界规则')
  })
})
