import { describe, expect, it, vi } from 'vitest'
import { consumeNdjson } from './ndjson'

describe('consumeNdjson', () => {
  it('keeps multibyte text and JSON split across transport chunks intact', async () => {
    const encoder = new TextEncoder()
    const payload = encoder.encode('{"type":"delta","text":"人物转身"}\n{"type":"candidate","revision":{"id":7}}\n')
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(payload.slice(0, 11))
        controller.enqueue(payload.slice(11, 29))
        controller.enqueue(payload.slice(29))
        controller.close()
      },
    })
    const onEvent = vi.fn()
    await consumeNdjson(stream, onEvent)
    expect(onEvent).toHaveBeenNthCalledWith(1, { type: 'delta', text: '人物转身' })
    expect(onEvent).toHaveBeenNthCalledWith(2, { type: 'candidate', revision: { id: 7 } })
  })

  it('does not invent a completed candidate when the stream ends after deltas', async () => {
    const stream = new Blob(['{"type":"delta","text":"未完成"}\n']).stream()
    const events: Array<Record<string, unknown>> = []
    await consumeNdjson(stream, event => events.push(event))
    expect(events).toEqual([{ type: 'delta', text: '未完成' }])
    expect(events.some(event => event.type === 'candidate')).toBe(false)
  })
})
