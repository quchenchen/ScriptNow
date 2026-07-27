import { describe, expect, it } from 'vitest'

import {
  anchorDisplayLabel,
  categoryDisplayLabel,
  fieldDisplayLabel,
  scriptBlueprintCategory,
} from './semanticLabels'

describe('creator semantic labels', () => {
  it('turns stable blueprint keys into creator-facing labels', () => {
    expect(categoryDisplayLabel('worldview')).toBe('世界观')
    expect(anchorDisplayLabel('world:era', 'worldview')).toBe('时代与历史')
    expect(anchorDisplayLabel('world:geography', 'worldview')).toBe('地理与空间')
    expect(fieldDisplayLabel('facts')).toBe('关键事实')
    expect(fieldDisplayLabel('dramatic_consequence')).toBe('戏剧后果')
  })

  it('keeps unknown extension keys visible instead of dropping information', () => {
    expect(anchorDisplayLabel('custom:signal', 'custom')).toBe('custom')
    expect(fieldDisplayLabel('custom_field')).toBe('custom_field')
  })

  it('maps historic provider blueprint kinds to the stable script categories', () => {
    expect(scriptBlueprintCategory('world_rule')).toBe('worldview')
    expect(scriptBlueprintCategory('relationship')).toBe('character')
    expect(scriptBlueprintCategory('key-event')).toBe('event')
    expect(scriptBlueprintCategory('setup')).toBe('foreshadow')
  })
})
