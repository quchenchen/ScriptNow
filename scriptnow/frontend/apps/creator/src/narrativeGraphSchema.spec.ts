import { describe, expect, it } from 'vitest'
import {
  canonicalNarrativeNodeType,
  canonicalNarrativeRelationType,
} from './narrativeGraphSchema'

describe('narrative graph taxonomy compatibility', () => {
  it('normalizes known historical node and relation aliases', () => {
    expect(canonicalNarrativeNodeType('world-rule')).toBe('concept')
    expect(canonicalNarrativeNodeType('faction')).toBe('organization')
    expect(canonicalNarrativeRelationType('participates_in')).toBe('affiliation')
    expect(canonicalNarrativeRelationType('protects')).toBe('emotional')
  })

  it('returns undefined for unknown values so the view can apply its safe fallback', () => {
    expect(canonicalNarrativeNodeType('unexpected_legacy_type')).toBeUndefined()
    expect(canonicalNarrativeRelationType('unexpected_legacy_relation')).toBeUndefined()
  })
})
