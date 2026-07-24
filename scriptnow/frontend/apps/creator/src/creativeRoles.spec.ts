import { describe, expect, it } from 'vitest'

import { creativeRoleLabel } from './creativeRoles'

describe('creative role display names', () => {
  it('presents friendly role names without changing runtime role keys', () => {
    expect(creativeRoleLabel('director')).toBe('灵感导演')
    expect(creativeRoleLabel('architect')).toBe('故事建筑师')
    expect(creativeRoleLabel('writer')).toBe('主笔')
    expect(creativeRoleLabel('reviewer')).toBe('审读编辑')
  })

  it('keeps an explicit fallback for roles introduced later', () => {
    expect(creativeRoleLabel('producer', '制片人')).toBe('制片人')
  })
})
