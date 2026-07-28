<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { api } from '../api'

interface TranslationChapter {
  chapter_id: string
  title: string
  source_text: string | null
  translated_title: string | null
  translated_text: string | null
  status: 'pending' | 'completed'
}

interface TranslationVersion {
  id: string
  version: number
  name: string
  chapter_count: number
  word_count: number
  created_at: string
}

interface GlossaryEntry {
  id: string
  source_term: string
  target_term: string
  status: 'candidate' | 'confirmed'
  source: 'automatic' | 'manual'
  pending_corrections: number
}

const props = defineProps<{
  projectId: string
  sourceLanguage?: string
  targetLanguage?: string
}>()

const chapters = ref<TranslationChapter[]>([])
const glossary = ref<GlossaryEntry[]>([])
const newSourceTerm = ref('')
const newTargetTerm = ref('')
const savingTerm = ref<string>()
const busyChapter = ref<string>()
const translatingAll = ref(false)
const loading = ref(true)
const error = ref('')
const notice = ref('')
const comparedChapter = ref<string>()
const showHistory = ref(false)
const versions = ref<TranslationVersion[]>([])
const versionName = ref('')
const savingVersion = ref(false)
const restoringVersion = ref<string>()
const showImport = ref(false)
const importChapterId = ref('')
const importFile = ref<File>()
const importing = ref(false)

const completedCount = computed(() => chapters.value.filter((chapter) => chapter.status === 'completed').length)
const pendingCount = computed(() => chapters.value.length - completedCount.value)
const progress = computed(() => chapters.value.length ? Math.round(completedCount.value / chapters.value.length * 100) : 0)

interface TranslationRunResponse {
  run_id: string
  status: 'queued' | 'running' | 'waiting' | 'succeeded' | 'failed' | 'cancelled'
  error_code?: string | null
}

async function waitForTranslationRun(runId: string) {
  const deadline = Date.now() + 10 * 60 * 1000
  while (Date.now() < deadline) {
    const run = await api<TranslationRunResponse>(
      `/translation/projects/${props.projectId}/runs/${runId}`,
    )
    if (run.status === 'succeeded') return
    if (run.status === 'failed' || run.status === 'cancelled') {
      throw new Error(run.error_code || '本章翻译未完成')
    }
    await new Promise((resolve) => window.setTimeout(resolve, 500))
  }
  throw new Error('本章翻译仍在后台运行，请稍后刷新查看')
}

async function enqueueChapterTranslation(chapter: TranslationChapter) {
  const run = await api<TranslationRunResponse>(
    `/translation/projects/${props.projectId}/chapters/${chapter.chapter_id}/translate?background=true`,
    { method: 'POST' },
  )
  await waitForTranslationRun(run.run_id)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [chapterList, glossaryResult] = await Promise.all([
      api<TranslationChapter[]>(`/translation/projects/${props.projectId}/chapters`),
      api<{ entries?: GlossaryEntry[] }>(`/translation/projects/${props.projectId}/glossary`),
    ])
    chapters.value = chapterList
    glossary.value = glossaryResult.entries ?? []
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '无法读取翻译项目'
  } finally {
    loading.value = false
  }
}

async function translateChapter(chapter: TranslationChapter) {
  busyChapter.value = chapter.chapter_id
  error.value = ''
  notice.value = `正在翻译《${chapter.title}》…`
  try {
    await enqueueChapterTranslation(chapter)
    notice.value = `《${chapter.title}》翻译完成`
    await load()
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '本章翻译失败'
    notice.value = ''
  } finally {
    busyChapter.value = undefined
  }
}

async function translateAll() {
  translatingAll.value = true
  error.value = ''
  const pending = chapters.value.filter((chapter) => chapter.status === 'pending')
  notice.value = `正在按章节顺序翻译 ${pending.length} 章，并同步术语…`
  try {
    let translated = 0
    for (const chapter of pending) {
      notice.value = `正在翻译第 ${translated + 1} / ${pending.length} 章：《${chapter.title}》`
      await enqueueChapterTranslation(chapter)
      translated += 1
    }
    notice.value = `本次完成 ${translated} 章`
    await load()
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '批量翻译失败'
    notice.value = ''
  } finally {
    translatingAll.value = false
  }
}

function toggleComparison(chapter: TranslationChapter) {
  comparedChapter.value = comparedChapter.value === chapter.chapter_id
    ? undefined
    : chapter.chapter_id
}

async function openHistory() {
  showHistory.value = true
  error.value = ''
  try {
    versions.value = await api<TranslationVersion[]>(
      `/translation/projects/${props.projectId}/versions`,
    )
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '无法读取译文历史版本'
  }
}

async function saveVersion() {
  if (!versionName.value.trim()) return
  savingVersion.value = true
  try {
    await api(`/translation/projects/${props.projectId}/versions`, {
      method: 'POST',
      body: JSON.stringify({ name: versionName.value.trim() }),
    })
    versionName.value = ''
    await openHistory()
    notice.value = '当前译文已保存为历史版本'
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '保存译文版本失败'
  } finally {
    savingVersion.value = false
  }
}

async function restoreVersion(version: TranslationVersion) {
  restoringVersion.value = version.id
  try {
    await api(
      `/translation/projects/${props.projectId}/versions/${version.id}/restore`,
      { method: 'POST' },
    )
    showHistory.value = false
    notice.value = `已恢复译文版本 v${version.version}，原有修订仍保留在历史中`
    await load()
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '恢复译文版本失败'
  } finally {
    restoringVersion.value = undefined
  }
}

async function exportTranslation() {
  error.value = ''
  try {
    const response = await fetch(
      `/api/translation/projects/${props.projectId}/export.docx`,
      { credentials: 'include' },
    )
    if (!response.ok) {
      const payload = await response.json().catch(() => ({})) as { detail?: string }
      throw new Error(payload.detail || `导出失败（${response.status}）`)
    }
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `translation-${props.projectId}.docx`
    anchor.click()
    URL.revokeObjectURL(url)
    notice.value = `已导出 ${completedCount.value} 章译文`
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '导出译文失败'
  }
}

function openImport() {
  showImport.value = true
  importChapterId.value ||= chapters.value[0]?.chapter_id ?? ''
}

async function importTranslation() {
  if (!importChapterId.value || !importFile.value) return
  importing.value = true
  error.value = ''
  try {
    const form = new FormData()
    form.set('chapter_id', importChapterId.value)
    form.set('file', importFile.value)
    await api(`/translation/projects/${props.projectId}/imports`, {
      method: 'POST',
      body: form,
    })
    showImport.value = false
    importFile.value = undefined
    notice.value = '人工译文已导入并形成新的章节修订'
    await load()
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '导入译文失败'
  } finally {
    importing.value = false
  }
}

function selectImportFile(event: Event) {
  importFile.value = (event.target as HTMLInputElement).files?.[0]
}

async function createTerm() {
  if (!newSourceTerm.value.trim() || !newTargetTerm.value.trim()) return
  savingTerm.value = 'new'
  try {
    await api(`/translation/projects/${props.projectId}/glossary`, {
      method: 'POST',
      body: JSON.stringify({
        source_term: newSourceTerm.value.trim(),
        target_term: newTargetTerm.value.trim(),
        status: 'confirmed',
      }),
    })
    newSourceTerm.value = ''
    newTargetTerm.value = ''
    await load()
    notice.value = '术语已确认，后续章节将优先使用该译法'
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '保存术语失败'
  } finally {
    savingTerm.value = undefined
  }
}

async function saveTerm(entry: GlossaryEntry) {
  if (!entry.source_term.trim() || !entry.target_term.trim()) return
  savingTerm.value = entry.id
  try {
    await api(`/translation/projects/${props.projectId}/glossary/${entry.id}`, {
      method: 'PUT',
      body: JSON.stringify({
        source_term: entry.source_term.trim(),
        target_term: entry.target_term.trim(),
        status: 'confirmed',
      }),
    })
    await load()
    const refreshed = glossary.value.find((item) => item.id === entry.id)
    notice.value = refreshed?.pending_corrections
      ? `固定译法已更新；${refreshed.pending_corrections} 章仍使用旧译法，请确认后应用纠偏`
      : '术语译法已更新，后续章节将使用新译法'
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '更新术语失败'
  } finally {
    savingTerm.value = undefined
  }
}

async function applyCorrections(entry: GlossaryEntry) {
  savingTerm.value = entry.id
  error.value = ''
  try {
    const result = await api<{ updated_chapters: number }>(
      `/translation/projects/${props.projectId}/glossary/corrections/apply`,
      {
        method: 'POST',
        body: JSON.stringify({ term_id: entry.id }),
      },
    )
    notice.value = result.updated_chapters
      ? `已按确认译法修订 ${result.updated_chapters} 章，并保留原译文修订`
      : '没有需要修改的旧译法'
    await load()
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '术语纠偏失败'
  } finally {
    savingTerm.value = undefined
  }
}

async function deleteTerm(entry: GlossaryEntry) {
  savingTerm.value = entry.id
  try {
    await api(`/translation/projects/${props.projectId}/glossary/${entry.id}`, {
      method: 'DELETE',
    })
    await load()
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '删除术语失败'
  } finally {
    savingTerm.value = undefined
  }
}

onMounted(() => {
  void load()
  window.addEventListener('scriptnow:translation-import', openImport)
  window.addEventListener('scriptnow:translation-history', openHistory)
})
onUnmounted(() => {
  window.removeEventListener('scriptnow:translation-import', openImport)
  window.removeEventListener('scriptnow:translation-history', openHistory)
})
</script>

<template>
  <section class="translation-studio">
    <header class="translation-hero">
      <div>
        <p class="eyebrow">文学翻译 · 忠实模式</p>
        <h2>逐章翻译，统一作品语言。</h2>
        <p>保留原作的世界观、情节、语气与结构；译文独立保存，不改动源作品正文。</p>
      </div>
      <div class="translation-language-pair">
        <span>{{ sourceLanguage || '源语言' }}</span>
        <b>→</b>
        <span>{{ targetLanguage || '目标语言' }}</span>
      </div>
      <div class="translation-actions">
        <button class="secondary" type="button" @click="openHistory">历史版本</button>
        <button
          class="primary"
          type="button"
          :disabled="!completedCount"
          @click="exportTranslation"
        >
          导出译文
        </button>
      </div>
    </header>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="notice" class="translation-notice" role="status">{{ notice }}</p>

    <section class="translation-progress-card">
      <div>
        <strong>{{ completedCount }} / {{ chapters.length }} 章已完成</strong>
        <span v-if="pendingCount">{{ pendingCount }} 章待翻译</span>
        <span v-else>全部章节已经完成</span>
      </div>
      <div class="translation-progress" :aria-label="`翻译进度 ${progress}%`">
        <i :style="{ width: `${progress}%` }" />
      </div>
      <button
        class="primary"
        type="button"
        :disabled="loading || translatingAll || busyChapter !== undefined || !pendingCount"
        @click="translateAll"
      >
        {{ translatingAll ? '正在翻译整部作品…' : pendingCount ? '翻译全部待处理章节' : '翻译已完成' }}
      </button>
    </section>

    <div v-if="loading" class="translation-empty">正在读取章节与术语…</div>
    <div v-else-if="!chapters.length" class="translation-empty">
      <h3>源作品还没有可翻译的章节</h3>
      <p>请先回到源作品确认 StoryMap，并至少完成一章正文。</p>
    </div>
    <div v-else class="translation-chapter-list">
      <article v-for="(chapter, index) in chapters" :key="chapter.chapter_id" class="translation-chapter">
        <header>
          <span>{{ String(index + 1).padStart(2, '0') }}</span>
          <div>
            <h3>{{ chapter.translated_title || chapter.title }}</h3>
            <p v-if="chapter.translated_title" class="translation-source-title">原题 · {{ chapter.title }}</p>
            <small :class="{ completed: chapter.status === 'completed' }">
              {{ chapter.status === 'completed' ? '译文已完成' : '等待翻译' }}
            </small>
          </div>
          <button
            v-if="chapter.status !== 'completed'"
            class="secondary"
            type="button"
            :disabled="translatingAll || busyChapter !== undefined"
            @click="translateChapter(chapter)"
          >
            {{ busyChapter === chapter.chapter_id ? '翻译中…' : '翻译本章' }}
          </button>
          <button
            v-else
            class="secondary"
            type="button"
            :aria-expanded="comparedChapter === chapter.chapter_id"
            @click="toggleComparison(chapter)"
          >
            {{ comparedChapter === chapter.chapter_id ? '收起对照' : '原文 / 译文对照' }}
          </button>
        </header>
        <div
          v-if="chapter.translated_text && comparedChapter === chapter.chapter_id"
          class="translation-comparison"
        >
          <section>
            <small>{{ sourceLanguage || '原文' }}</small>
            <h4>{{ chapter.title }}</h4>
            <p>{{ chapter.source_text || '源正文暂不可用。' }}</p>
          </section>
          <section>
            <small>{{ targetLanguage || '译文' }}</small>
            <h4>{{ chapter.translated_title || chapter.title }}</h4>
            <p>{{ chapter.translated_text }}</p>
          </section>
        </div>
        <p v-else-if="chapter.translated_text" class="translation-preview">{{ chapter.translated_text }}</p>
        <p v-else class="translation-preview empty">完成后将在这里显示译文预览。</p>
      </article>
    </div>

    <aside class="translation-glossary">
      <div class="translation-glossary-intro">
        <p class="eyebrow">术语一致性</p>
        <h3>作品术语表</h3>
        <p>每章完成后补充候选；确认后进入后续翻译上下文。修改固定译法时，已使用旧译法的章节会进入待纠偏队列，不会被静默改写。</p>
      </div>
      <div class="translation-glossary-workspace">
        <form class="translation-term-form" @submit.prevent="createTerm">
          <input v-model="newSourceTerm" maxlength="240" :placeholder="`${sourceLanguage || '原文'}术语`" />
          <span>→</span>
          <input v-model="newTargetTerm" maxlength="240" :placeholder="`${targetLanguage || '译文'}固定译法`" />
          <button
            class="primary"
            type="submit"
            :disabled="savingTerm !== undefined || !newSourceTerm.trim() || !newTargetTerm.trim()"
          >
            确认术语
          </button>
        </form>
        <div v-if="glossary.length" class="translation-term-list">
          <article v-for="entry in glossary" :key="entry.id">
            <input v-model="entry.source_term" maxlength="240" aria-label="原文术语" />
            <span>→</span>
            <input v-model="entry.target_term" maxlength="240" aria-label="固定译法" placeholder="填写译法后确认" />
            <small :class="entry.status">
              {{ entry.status === 'confirmed' ? '已确认' : '待确认' }}
            </small>
            <button
              v-if="entry.pending_corrections"
              class="secondary"
              type="button"
              :disabled="savingTerm !== undefined"
              @click="applyCorrections(entry)"
            >
              纠偏 {{ entry.pending_corrections }} 章
            </button>
            <button
              class="secondary"
              type="button"
              :disabled="savingTerm !== undefined || !entry.target_term.trim()"
              @click="saveTerm(entry)"
            >
              {{ savingTerm === entry.id ? '保存中…' : '保存' }}
            </button>
            <button
              class="text-button danger"
              type="button"
              :disabled="savingTerm !== undefined"
              @click="deleteTerm(entry)"
            >
              删除
            </button>
          </article>
        </div>
        <p v-else class="muted">尚无术语。可先添加人物名、地名或作品专有设定。</p>
      </div>
    </aside>

    <div v-if="showHistory" class="translation-modal-backdrop" @click.self="showHistory = false">
      <section class="translation-history-modal" role="dialog" aria-modal="true" aria-label="译文历史版本">
        <header>
          <div>
            <p class="eyebrow">译文历史</p>
            <h3>保存与恢复译文版本</h3>
          </div>
          <button class="icon-button" type="button" aria-label="关闭" @click="showHistory = false">×</button>
        </header>
        <form class="translation-version-form" @submit.prevent="saveVersion">
          <input v-model="versionName" maxlength="160" placeholder="例如：术语统一后的版本" />
          <button class="primary" type="submit" :disabled="savingVersion || !versionName.trim()">
            {{ savingVersion ? '保存中…' : '保存当前版本' }}
          </button>
        </form>
        <div v-if="versions.length" class="translation-version-list">
          <article v-for="version in versions" :key="version.id">
            <div>
              <strong>v{{ version.version }} · {{ version.name }}</strong>
              <span>
                {{ version.chapter_count }} 章 · {{ version.word_count }} 字符 ·
                {{ new Date(version.created_at).toLocaleString() }}
              </span>
            </div>
            <button
              class="secondary"
              type="button"
              :disabled="restoringVersion !== undefined"
              @click="restoreVersion(version)"
            >
              {{ restoringVersion === version.id ? '恢复中…' : '恢复此版本' }}
            </button>
          </article>
        </div>
        <p v-else class="translation-empty">尚未保存译文历史版本。</p>
      </section>
    </div>

    <div v-if="showImport" class="translation-modal-backdrop" @click.self="showImport = false">
      <section class="translation-history-modal" role="dialog" aria-modal="true" aria-label="导入译文">
        <header>
          <div>
            <p class="eyebrow">人工译稿</p>
            <h3>导入到指定章节</h3>
            <p class="muted">支持 UTF-8 TXT 和 DOCX。导入后成为当前译文，原修订仍保留。</p>
          </div>
          <button class="icon-button" type="button" aria-label="关闭" @click="showImport = false">×</button>
        </header>
        <form class="translation-import-form" @submit.prevent="importTranslation">
          <label>
            <span>目标章节</span>
            <select v-model="importChapterId">
              <option v-for="(chapter, index) in chapters" :key="chapter.chapter_id" :value="chapter.chapter_id">
                {{ index + 1 }} · {{ chapter.title }}
              </option>
            </select>
          </label>
          <label>
            <span>译文文件</span>
            <input type="file" accept=".txt,.docx,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document" @change="selectImportFile" />
          </label>
          <button class="primary" type="submit" :disabled="importing || !importChapterId || !importFile">
            {{ importing ? '导入中…' : '导入并创建修订' }}
          </button>
        </form>
      </section>
    </div>
  </section>
</template>
