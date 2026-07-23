export type MessageBlock = {
  type: 'heading' | 'paragraph' | 'list' | 'divider'
  text?: string
  items?: string[]
  level?: number
  ordered?: boolean
}

function cleanInline(value: string): string {
  return value.replace(/\*\*(.*?)\*\*/g, '$1').replace(/`([^`]+)`/g, '$1').replace(/^[-*]\s+/, '').trim()
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
  for (const raw of value.replace(/\r/g, '').split('\n')) {
    const line = raw.trim()
    if (!line) { flushParagraph(); flushList(); continue }
    const heading = line.match(/^(#{1,4})\s+(.+)$/)
    const orderedItem = line.match(/^\d+\.\s+(.+)$/)
    const bulletItem = line.match(/^[-*]\s+(.+)$/)
    const letterItem = line.match(/^\*\*([A-Z])\*\*[:：]?\s*(.+)$/)
    if (heading) {
      flushParagraph(); flushList(); blocks.push({ type: 'heading', level: heading[1].length, text: cleanInline(heading[2]) })
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
