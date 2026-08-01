export type MessageBlock = {
  type: 'heading' | 'paragraph' | 'list' | 'divider' | 'table' | 'quote' | 'code'
  text?: string
  items?: string[]
  level?: number
  ordered?: boolean
  headers?: string[]
  rows?: string[][]
}

function cleanInline(value: string): string {
  return value.replace(/\*\*(.*?)\*\*/g, '$1').replace(/`([^`]+)`/g, '$1').replace(/^[-*]\s+/, '').trim()
}

function expandCollapsedTables(value: string): string {
  return value.replace(
    /(\|[^|\n]+(?:\|[^|\n]+){1,}\|)\s+\|(\s*:?-{3,}:?(?:\s*\|\s*:?-{3,}:?){1,}\s*\|)(?=\s+\|)/g,
    '$1\n|$2',
  ).replace(/\|\s+\|(?=[^|\n]+\|)/g, '|\n|')
}

export function parseAgentMessage(value: string): MessageBlock[] {
  const blocks: MessageBlock[] = []
  let paragraph: string[] = []
  let list: string[] = []
  let listOrdered: boolean | undefined
  const flushParagraph = () => { if (paragraph.length) blocks.push({ type: 'paragraph', text: cleanInline(paragraph.join(' ')) }); paragraph = [] }
  const flushList = () => {
    if (list.length) blocks.push({ type: 'list', ordered: listOrdered, items: [...list] })
    list = []
    listOrdered = undefined
  }
  const lines = expandCollapsedTables(value.replace(/\r/g, '')).split('\n')
  const tableCells = (line: string) => line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map(cleanInline)
  const isTableDivider = (line: string) => {
    const cells = tableCells(line)
    return cells.length > 1 && cells.every((cell) => /^:?-{3,}:?$/.test(cell))
  }
  for (let index = 0; index < lines.length; index += 1) {
    const raw = lines[index]
    const line = raw.trim()
    if (!line) { flushParagraph(); flushList(); continue }
    if (line.startsWith('```')) {
      flushParagraph()
      flushList()
      const code: string[] = []
      index += 1
      while (index < lines.length && !lines[index].trim().startsWith('```')) {
        code.push(lines[index])
        index += 1
      }
      blocks.push({ type: 'code', text: code.join('\n') })
      continue
    }
    const nextLine = lines[index + 1]?.trim() ?? ''
    if (line.includes('|') && isTableDivider(nextLine)) {
      flushParagraph()
      flushList()
      const headers = tableCells(line)
      const rows: string[][] = []
      index += 2
      while (index < lines.length) {
        const row = lines[index].trim()
        if (!row || !row.includes('|')) {
          index -= 1
          break
        }
        const cells = tableCells(row)
        rows.push(headers.map((_, cellIndex) => cells[cellIndex] ?? ''))
        index += 1
      }
      blocks.push({ type: 'table', headers, rows })
      continue
    }
    const heading = line.match(/^(#{1,4})\s+(.+)$/)
    const orderedItem = line.match(/^\d+\.\s+(.+)$/)
    const bulletItem = line.match(/^[-*]\s+(.+)$/)
    const letterItem = line.match(/^\*\*([A-Z])\*\*[:：]?\s*(.+)$/)
    if (heading) {
      flushParagraph(); flushList(); blocks.push({ type: 'heading', level: heading[1].length, text: cleanInline(heading[2]) })
    } else if (line.startsWith('>')) {
      flushParagraph(); flushList(); blocks.push({ type: 'quote', text: cleanInline(line.replace(/^>\s?/, '')) })
    } else if (/^---+$/.test(line)) {
      flushParagraph(); flushList(); blocks.push({ type: 'divider' })
    } else if (orderedItem || bulletItem || letterItem) {
      flushParagraph()
      const ordered = Boolean(orderedItem)
      if (list.length && listOrdered !== ordered) flushList()
      listOrdered = ordered
      const content = orderedItem?.[1] ?? bulletItem?.[1] ?? `${letterItem?.[1]}：${letterItem?.[2]}`
      list.push(cleanInline(content))
    } else {
      flushList(); paragraph.push(line)
    }
  }
  flushParagraph(); flushList()
  return blocks
}
