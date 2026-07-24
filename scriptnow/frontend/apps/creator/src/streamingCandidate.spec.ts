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
})
