import { describe, expect, it } from 'vitest'

import { streamedCandidateBlocks } from './streamingCandidate'

describe('streamedCandidateBlocks', () => {
  it('extracts complete blocks across a joined stream', () => {
    const source = '{"blocks":[{"type":"heading","text":"Forty-Three Coins"},{"type":"prose","text":"I count forty-three."}]}'
    expect(streamedCandidateBlocks(source)).toEqual([
      { block_id: 'stream-0', type: 'heading', text: 'Forty-Three Coins' },
      { block_id: 'stream-1', type: 'prose', text: 'I count forty-three.' },
    ])
  })

  it('decodes escaped prose and hides an unfinished block', () => {
    const source = '{"type":"dialogue","text":"She says, \\"Go.\\"\\nNow."},{"type":"prose","text":"unfinished'
    expect(streamedCandidateBlocks(source)).toEqual([
      { block_id: 'stream-0', type: 'dialogue', text: 'She says, "Go."\nNow.' },
    ])
  })

  it('strips JSON wrapper from Chinese prose blocks', () => {
    const source = '{"blocks":[{"type":"prose","text":"我继续走。客厅的角落"},{"type":"prose","text":"我伸手去拿那只杯子"}]}'
    expect(streamedCandidateBlocks(source)).toEqual([
      { block_id: 'stream-0', type: 'prose', text: '我继续走。客厅的角落' },
      { block_id: 'stream-1', type: 'prose', text: '我伸手去拿那只杯子' },
    ])
  })
})
