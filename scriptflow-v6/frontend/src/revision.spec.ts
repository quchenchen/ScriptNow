import { describe, expect, it } from 'vitest'
import { replaceSelection, revisionPayload, selectionFromRange } from './revision'

describe('selection revision contract', () => {
  it('normalizes a backwards selection and replaces only that range', () => {
    const selection = selectionFromRange('甲推门。乙回头。', 7, 4)!
    expect(selection.text).toBe('乙回头')
    expect(replaceSelection('甲推门。乙回头。', selection, '乙猛然回头')).toBe('甲推门。乙猛然回头。')
  })

  it('builds a brief and context pack that preserve unselected prose', () => {
    const selection = selectionFromRange('开场\n旧对白\n收尾', 3, 6)!
    const payload = revisionPayload('开场\n旧对白\n收尾', selection, '对白更克制', '新对白')
    expect(payload.candidate_content).toBe('开场\n新对白\n收尾')
    expect(payload.brief.preserve).toContain('选区外正文')
    expect(payload.context_pack.anchors.selected_text).toBe('旧对白')
  })
})
