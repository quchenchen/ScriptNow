export const productName = 'ScriptNow'

export type AppSurface = 'creator' | 'admin'

export { useLocale, type Locale, type MessageKey } from './i18n'
export { installLocaleDirective } from './localeDirective'
export { sourceMessages, translateSourceMessage } from './sourceMessages'
export { useTheme, type ResolvedTheme, type ThemePreference } from './theme'
