export interface StreamingNovelBlock {
  block_id: string
  type: string
  text: string
}

export function streamedCandidateBlocks(source: string): StreamingNovelBlock[] {
  const blocks: StreamingNovelBlock[] = []
  // Strip JSON wrapper noise: {"blocks":[ and trailing ]} etc.
  // Remove leading JSON structure characters that leak through SSE
  // before the prose/dialogue block patterns.
  // The writer agent output has shape {"blocks": [{"type":"prose","text":"..."}]}
  // we only want the inner block objects.
  const stripped = source
    .replace(/^\s*\{\s*"blocks"\s*:\s*\[/g, '')
    .replace(/\]\s*\}$/g, '')
  const pattern = /"type"\s*:\s*"(heading|prose|dialogue|quote|divider)"\s*,\s*"(?:text|content)"\s*:\s*"((?:\\.|[^"\\])*)"/g
  for (const match of stripped.matchAll(pattern)) {
    try {
      blocks.push({
        block_id: `stream-${blocks.length}`,
        type: match[1],
        text: JSON.parse(`"${match[2]}"`) as string,
      })
    } catch {
      // Incomplete JSON strings stay hidden until a later stream chunk closes them.
    }
  }
  return blocks
}
