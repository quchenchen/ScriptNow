export interface StreamingNovelBlock {
  block_id: string
  type: string
  text: string
}

export function streamedCandidateBlocks(source: string): StreamingNovelBlock[] {
  const blocks: StreamingNovelBlock[] = []
  const pattern = /"type"\s*:\s*"(heading|prose|dialogue|quote|divider)"\s*,\s*"(?:text|content)"\s*:\s*"((?:\\.|[^"\\])*)"/g
  for (const match of source.matchAll(pattern)) {
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
