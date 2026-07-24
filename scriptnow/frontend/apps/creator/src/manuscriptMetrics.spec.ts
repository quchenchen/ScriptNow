import { describe, expect, it } from 'vitest'

import { manuscriptMetrics, manuscriptProgress } from './manuscriptMetrics'

describe('manuscriptMetrics', () => {
  it('counts English words instead of non-whitespace characters', () => {
    expect(manuscriptMetrics([{ text: "The wolf's oath is broken." }], 'en-US')).toEqual({
      count: 5,
      unit: 'words',
    })
  })

  it('counts Chinese characters and Latin terms as writing units', () => {
    expect(manuscriptMetrics([{ text: '月蚀之契 AI' }], 'zh-CN')).toEqual({
      count: 5,
      unit: '字',
    })
  })

  it('reports a visible target band', () => {
    expect(manuscriptProgress([{ text: 'one two three four' }], 'en-US', 3).status).toBe('over')
    expect(manuscriptProgress([{ text: 'one two three four five six' }], 'en-US', 5).status).toBe('on-target')
  })
})
