import type { App, DirectiveBinding, ObjectDirective } from 'vue'

import type { Locale } from './i18n'
import { translateExactSourceMessage } from './sourceMessages'

const attributes = ['aria-label', 'placeholder', 'title']
const authoredText = new WeakMap<Node, string>()
const authoredAttributes = new WeakMap<Element, Map<string, string>>()
const renderedText = new WeakMap<Node, string>()
const renderedAttributes = new WeakMap<Element, Map<string, string>>()
const containsHan = (value: string) => /\p{Script=Han}/u.test(value)
const protectedContent = [
  '[data-i18n-skip]',
  '[contenteditable="true"]',
  '.agent-message',
  '.novel-page',
  '.screenplay-page',
  '.source-evidence-list p',
  '.evidence-preview p',
  '.graph-meaning p',
  '.graph-relations button',
  '.graph-evidence button',
].join(',')

function translate(value: string, locale: Locale): string {
  if (locale === 'en-US') return translateExactSourceMessage(value)
  return value
}

function localizeNode(node: Node, locale: Locale) {
  const owner = node instanceof Element ? node : node.parentElement
  if (owner?.closest(protectedContent)) return
  if (node.nodeType === Node.TEXT_NODE && node.textContent?.trim()) {
    const current = node.textContent
    if (current !== renderedText.get(node)) {
      if (containsHan(current)) authoredText.set(node, current)
      else authoredText.delete(node)
    }
    const source = authoredText.get(node)
    const translated = locale === 'zh-CN' && source ? source : translate(source ?? current, locale)
    renderedText.set(node, translated)
    if (translated !== current) node.textContent = translated
    return
  }
  if (!(node instanceof Element)) return
  for (const attribute of attributes) {
    const value = node.getAttribute(attribute)
    if (!value) continue
    let sources = authoredAttributes.get(node)
    if (!sources) {
      sources = new Map()
      authoredAttributes.set(node, sources)
    }
    let rendered = renderedAttributes.get(node)
    if (!rendered) {
      rendered = new Map()
      renderedAttributes.set(node, rendered)
    }
    if (value !== rendered.get(attribute)) {
      if (containsHan(value)) sources.set(attribute, value)
      else sources.delete(attribute)
    }
    const source = sources.get(attribute)
    const translated = locale === 'zh-CN' && source ? source : translate(source ?? value, locale)
    rendered.set(attribute, translated)
    if (translated !== value) node.setAttribute(attribute, translated)
  }
  for (const child of node.childNodes) localizeNode(child, locale)
}

interface LocalizedElement extends HTMLElement {
  __scriptnowLocaleObserver?: MutationObserver
  __scriptnowLocale?: Locale
}

function apply(root: LocalizedElement, locale: Locale) {
  root.__scriptnowLocale = locale
  localizeNode(root, locale)
}

const localeDirective: ObjectDirective<LocalizedElement, Locale> = {
    mounted(element: LocalizedElement, binding: DirectiveBinding<Locale>) {
      apply(element, binding.value)
      element.__scriptnowLocaleObserver = new MutationObserver((records) => {
        const locale = element.__scriptnowLocale ?? binding.value
        for (const record of records) {
          if (record.type === 'characterData') localizeNode(record.target, locale)
          if (record.type === 'attributes') localizeNode(record.target, locale)
          for (const node of record.addedNodes) localizeNode(node, locale)
        }
      })
      element.__scriptnowLocaleObserver.observe(element, {
        childList: true,
        characterData: true,
        attributes: true,
        attributeFilter: attributes,
        subtree: true,
      })
    },
    updated(element: LocalizedElement, binding: DirectiveBinding<Locale>) {
      apply(element, binding.value)
    },
    unmounted(element: LocalizedElement) {
      element.__scriptnowLocaleObserver?.disconnect()
    },
}

export function installLocaleDirective(app: App) {
  app.directive('ui-locale', localeDirective)
  return localeDirective
}
