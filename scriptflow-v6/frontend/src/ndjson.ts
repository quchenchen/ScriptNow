export type NdjsonEvent = Record<string, unknown> & { type: string }

export async function consumeNdjson(
  stream: ReadableStream<Uint8Array>,
  onEvent: (event: NdjsonEvent) => void,
): Promise<void> {
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  let pending = ''
  while (true) {
    const { done, value } = await reader.read()
    pending += decoder.decode(value ?? new Uint8Array(), { stream: !done })
    const lines = pending.split('\n')
    pending = lines.pop() ?? ''
    for (const line of lines) {
      if (line.trim()) onEvent(JSON.parse(line) as NdjsonEvent)
    }
    if (done) break
  }
  if (pending.trim()) onEvent(JSON.parse(pending) as NdjsonEvent)
}
