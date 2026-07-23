import { beforeEach, describe, expect, it } from 'vitest'
import { useLocale } from '@scriptflow/shared'

describe('shared interface locale', () => {
  beforeEach(() => useLocale().setLocale('zh-CN'))

  it('persists the selected locale and updates the document language', () => {
    const i18n = useLocale()
    i18n.setLocale('en-US')

    expect(i18n.locale.value).toBe('en-US')
    expect(i18n.t('creator.ideation')).toBe('Ideation')
    expect(window.localStorage.getItem('scriptflow-ui-locale')).toBe('en-US')
    expect(document.documentElement.lang).toBe('en-US')
  })

  it('keeps both application surfaces on the same singleton locale', () => {
    const creator = useLocale()
    const admin = useLocale()
    creator.toggleLocale()

    expect(admin.locale.value).toBe('en-US')
    expect(admin.t('admin.supplyManagement')).toBe('Supply management')
  })
})
