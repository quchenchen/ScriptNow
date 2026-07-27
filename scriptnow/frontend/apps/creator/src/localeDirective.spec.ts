// @ts-nocheck -- Vitest runs this Node-backed governance test; browser app tsconfig intentionally excludes Node globals.
import { createApp, h, nextTick, ref } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { installLocaleDirective, sourceMessages, translateSourceMessage, useLocale } from '@scriptnow/shared'

const mounted: HTMLElement[] = []

afterEach(() => {
  mounted.splice(0).forEach((element) => element.remove())
  useLocale().setLocale('zh-CN')
})

describe('whole-application interface localization', () => {
  it('localizes existing and asynchronous UI copy without a reload', async () => {
    const message = ref('正在读取创作现场…')
    const root = document.createElement('div')
    document.body.append(root)
    mounted.push(root)

    const app = createApp({
      setup: () => () => h('main', { 'v-ui-locale': undefined }, [
        h('p', message.value),
        h('input', { placeholder: '搜索 Provider' }),
      ]),
    })
    const directive = installLocaleDirective(app)
    app.mount(root)

    const host = root.firstElementChild as HTMLElement
    directive?.mounted?.(host, { value: 'en-US' } as never, null as never, null as never)
    await nextTick()
    expect(host.textContent).toContain('Loading your creative studio')
    expect(host.querySelector('input')?.placeholder).toBe('Search Provider')

    message.value = '正在构建语义图谱…'
    await nextTick()
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(host.textContent).toContain('Building semantic graph')

    directive?.updated?.(host, { value: 'zh-CN' } as never, null as never, null as never)
    expect(host.textContent).toContain('正在构建语义图谱')
  })

  it('does not alter author-controlled content inside an explicit boundary', () => {
    const root = document.createElement('div')
    root.setAttribute('data-i18n-skip', '')
    root.textContent = '人物关系与创作语言'
    document.body.append(root)
    mounted.push(root)

    const app = createApp({ render: () => null })
    const directive = installLocaleDirective(app)
    directive?.mounted?.(root, { value: 'en-US' } as never, null as never, null as never)

    expect(root.textContent).toBe('人物关系与创作语言')
  })

  it('does not translate catalogue fragments inside author-authored text', () => {
    const root = document.createElement('div')
    root.textContent = '回声诊所·剧本全流程验收：让复制人格继续活下去，不可删除全部记录。'
    document.body.append(root)
    mounted.push(root)

    const app = createApp({ render: () => null })
    const directive = installLocaleDirective(app)
    directive?.mounted?.(root, { value: 'en-US' } as never, null as never, null as never)

    expect(root.textContent).toBe('回声诊所·剧本全流程验收：让复制人格继续活下去，不可删除全部记录。')
  })

  it('restores authored Chinese after an incomplete English source translation', async () => {
    const root = document.createElement('div')
    root.textContent = '灵感搭档暂时没有形成完整候选，请保留原始想法后重试。'
    document.body.append(root)
    mounted.push(root)

    const app = createApp({ render: () => null })
    const directive = installLocaleDirective(app)
    directive?.mounted?.(root, { value: 'en-US' } as never, null as never, null as never)
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(root.textContent).not.toBe('灵感搭档暂时没有形成完整候选，请保留原始想法后重试。')

    directive?.updated?.(root, { value: 'zh-CN' } as never, null as never, null as never)
    expect(root.textContent).toBe('灵感搭档暂时没有形成完整候选，请保留原始想法后重试。')
  })

  it('does not overwrite symbolic i18n output with a cached Chinese source fragment', async () => {
    const root = document.createElement('div')
    root.textContent = '项目仪表盘'
    document.body.append(root)
    mounted.push(root)

    const app = createApp({ render: () => null })
    const directive = installLocaleDirective(app)
    directive?.mounted?.(root, { value: 'zh-CN' } as never, null as never, null as never)

    root.textContent = 'Project dashboard'
    directive?.updated?.(root, { value: 'en-US' } as never, null as never, null as never)
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(root.textContent).toBe('Project dashboard')
  })

  it('keeps a substantial shared source catalogue for dense workflow surfaces', () => {
    expect(Object.keys(sourceMessages).length).toBeGreaterThan(350)
    expect(sourceMessages['故事时间线']).toBe('Story timeline')
    expect(sourceMessages['记忆策略更新失败']).toBe('Memory policy update failed')
  })

  it('rejects Chinese UI source that is missing from the shared catalogue', () => {
    const vueFiles = (directory: string): string[] => readdirSync(directory, { withFileTypes: true })
      .flatMap((entry) => entry.isDirectory()
        ? vueFiles(join(directory, entry.name))
        : entry.name.endsWith('.vue') ? [join(directory, entry.name)] : [])
    const uncovered = vueFiles(join(process.cwd(), 'apps'))
      .flatMap((file) => {
        const localizedSource = translateSourceMessage(readFileSync(file, 'utf8'))
        const runs = [...new Set(localizedSource.match(/[\p{Script=Han}]{2,}/gu) ?? [])]
        return runs.map((copy) => `${file.replace(`${process.cwd()}/`, '')}: ${copy}`)
      })

    expect(uncovered, uncovered.join('\n')).toEqual([])
  })
})
