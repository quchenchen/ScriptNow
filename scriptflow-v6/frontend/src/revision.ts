export type TextSelection = { start: number; end: number; text: string }

export function selectionFromRange(content: string, start: number, end: number): TextSelection | null {
  const from = Math.max(0, Math.min(start, end))
  const to = Math.min(content.length, Math.max(start, end))
  const text = content.slice(from, to)
  return text.trim() ? { start: from, end: to, text } : null
}

export function replaceSelection(content: string, selection: TextSelection, replacement: string): string {
  return `${content.slice(0, selection.start)}${replacement}${content.slice(selection.end)}`
}

export function revisionPayload(content: string, selection: TextSelection, instruction: string, replacement: string) {
  return {
    candidate_content: replaceSelection(content, selection, replacement),
    brief: { goal: instruction.trim(), scope: [selection.text], preserve: ['选区外正文'], constraints: ['不改写未选中的正文'] },
    context_pack: { anchors: { selected_text: selection.text, selection_start: selection.start, selection_end: selection.end }, source_refs: [], open_threads: [] },
    evidence: [{ type: 'selection', excerpt: selection.text }],
    impact: [{ type: 'scene_text', scope: 'selection_only' }],
  }
}
