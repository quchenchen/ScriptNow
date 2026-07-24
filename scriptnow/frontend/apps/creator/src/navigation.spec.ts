import { describe, expect, it } from 'vitest'

import { safeNextPath } from './navigation'

describe('safe login return path', () => {
  it('allows only known Creator routes', () => {
    expect(safeNextPath('/')).toBe('/')
    expect(safeNextPath('/projects/85da4b61-af5d-48dc-a9a6-733c73deed83')).toContain('/projects/')
    expect(safeNextPath('/new')).toBe('/new')
  })

  it('rejects malformed, unknown and cross-origin paths', () => {
    expect(safeNextPath('/。我将再次使用')).toBe('/')
    expect(safeNextPath('//attacker.example/path')).toBe('/')
    expect(safeNextPath('https://attacker.example/path')).toBe('/')
    expect(safeNextPath('/missing')).toBe('/')
  })
})
