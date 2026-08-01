<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useLocale } from '@scriptnow/shared'

import { api } from '../api'
import AgentMessage from '../components/AgentMessage.vue'
import AppShell from '../components/AppShell.vue'

interface ReviewCapabilities {
  review_domain: 'novel' | 'script'
  connected: boolean
  reviewer_ready: boolean
  coverage: string[]
}
interface ReviewMessage {
  id: string
  sequence: number
  actor: 'user' | 'assistant'
  content: string
  metadata?: Record<string, unknown>
}
interface ReviewCase {
  id: string
  title: string
  document_kind: 'novel' | 'script' | 'outline'
  review_domain: 'novel' | 'script'
  source_filename: string
  status: string
  messages: ReviewMessage[]
  updated_at: string
}
interface ReviewIntent {
  id: 'overall' | 'structure' | 'character' | 'pacing' | 'market' | 'adaptation'
  label: string
  instruction: string
}
interface EvidenceManifestItem {
  evidence_id: string
  start: number
  end: number
  reason: string
  preview: string
}

const { isEnglish } = useLocale()
const cases = ref<ReviewCase[]>([])
const activeCase = ref<ReviewCase>()
const capabilities = ref<ReviewCapabilities>()
const documentKind = ref<'novel' | 'script' | 'outline'>('novel')
const reviewDomain = ref<'novel' | 'script'>('novel')
const uploadFile = ref<File>()
const title = ref('')
const request = ref('')
const selectedIntentId = ref<ReviewIntent['id']>('overall')
const busy = ref(false)
const error = ref('')
const historyOpen = ref(false)

const canCreate = computed(() => Boolean(uploadFile.value) && !busy.value)
const reviewIntents = computed<ReviewIntent[]>(() => isEnglish.value
  ? [
      { id: 'overall', label: 'Overall', instruction: 'Give me an evidence-based overall review. Prioritize the most consequential strengths, risks, and revision actions.' },
      { id: 'structure', label: 'Structure', instruction: 'Review the story structure, causality, turning points, setup and payoff, and ending resolution.' },
      { id: 'character', label: 'Characters', instruction: 'Review character goals, agency, relationships, emotional change, and whether decisions are earned.' },
      { id: 'pacing', label: 'Pacing & hooks', instruction: 'Review pacing, information release, scene propulsion, chapter hooks, and where attention is likely to drop.' },
      { id: 'market', label: 'Audience & market', instruction: 'Review audience fit, genre promise, differentiation, commercial positioning, and likely reader expectations.' },
      { id: 'adaptation', label: 'Adaptation', instruction: 'Review screen adaptation potential, visual set pieces, production constraints, and the minimum viable adaptation path.' },
    ]
  : [
      { id: 'overall', label: '综合评审', instruction: '请进行基于原文证据的综合评审，优先指出最重要的优势、风险与修订行动。' },
      { id: 'structure', label: '故事结构', instruction: '请评审故事结构、因果链、转折、铺垫回收与结局闭合度。' },
      { id: 'character', label: '人物关系', instruction: '请评审人物目标、能动性、关系变化、情感弧线以及关键选择是否成立。' },
      { id: 'pacing', label: '节奏与钩子', instruction: '请评审节奏、信息释放、场景推进、章节钩子以及可能流失注意力的位置。' },
      { id: 'market', label: '受众与市场', instruction: '请评审目标受众匹配、类型承诺、差异化、市场定位与读者预期。' },
      { id: 'adaptation', label: '改编潜力', instruction: '请评审影视改编潜力、可视化场面、制作约束与最小可行改编路径。' },
    ])
const selectedIntent = computed(
  () => reviewIntents.value.find((intent) => intent.id === selectedIntentId.value) ?? reviewIntents.value[0],
)
const canSend = computed(() => Boolean(activeCase.value && selectedIntent.value) && !busy.value)
const hasConversation = computed(() => Boolean(activeCase.value?.messages.length))
const lastAssistantMessage = computed(
  () => [...(activeCase.value?.messages ?? [])].reverse().find((message) => message.actor === 'assistant'),
)
const canResume = computed(
  () => activeCase.value?.status === 'waiting' || lastAssistantMessage.value?.metadata?.recoverable === true,
)

function evidenceManifest(message: ReviewMessage): EvidenceManifestItem[] {
  const manifest = message.metadata?.evidence_manifest
  if (!Array.isArray(manifest)) return []
  return manifest.filter((item): item is EvidenceManifestItem => Boolean(
    item
    && typeof item === 'object'
    && typeof item.evidence_id === 'string'
    && typeof item.preview === 'string',
  ))
}

function pickFile(event: Event) {
  uploadFile.value = (event.target as HTMLInputElement).files?.[0]
  if (uploadFile.value && !title.value) {
    title.value = uploadFile.value.name.replace(/\.[^.]+$/, '')
  }
}
async function loadCapabilities() {
  capabilities.value = await api<ReviewCapabilities>(
    `/review-agent/capabilities?review_domain=${reviewDomain.value}`,
  )
}
async function changeDomain() {
  if (documentKind.value !== 'outline') documentKind.value = reviewDomain.value
  await loadCapabilities()
}
async function createCase() {
  if (!uploadFile.value) return
  busy.value = true
  error.value = ''
  try {
    const form = new FormData()
    form.append('file', uploadFile.value)
    form.append('document_kind', documentKind.value)
    form.append('review_domain', reviewDomain.value)
    if (title.value.trim()) form.append('title', title.value.trim())
    activeCase.value = await api<ReviewCase>('/review-agent/cases', {
      method: 'POST',
      body: form,
    })
    cases.value = [activeCase.value, ...cases.value.filter((item) => item.id !== activeCase.value?.id)]
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '无法创建评审会话'
  } finally {
    busy.value = false
  }
}
async function openCase(caseId: string) {
  error.value = ''
  try {
    activeCase.value = await api<ReviewCase>(`/review-agent/cases/${caseId}`)
    historyOpen.value = false
    reviewDomain.value = activeCase.value.review_domain
    await loadCapabilities()
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '无法读取评审会话'
  }
}
async function send() {
  if (!activeCase.value || !selectedIntent.value) return
  busy.value = true
  error.value = ''
  const detail = request.value.trim()
  const content = canResume.value && !detail
    ? (isEnglish.value
        ? 'Continue the interrupted review from the saved AgentScope state. Complete the current review focus without restarting the work.'
        : '请从已保存的 AgentScope 状态继续本轮评审，完成当前评审重点，不要重新开始。')
    : detail || (isEnglish.value
        ? 'Review this work using the selected focus and ground the findings in source evidence.'
        : '请按当前评审重点审读这部作品，并以原文证据支撑判断。')
  try {
    activeCase.value = await api<ReviewCase>(
      `/review-agent/cases/${activeCase.value.id}/messages`,
      {
        method: 'POST',
        body: JSON.stringify({
          content,
          idempotency_key: crypto.randomUUID(),
          language: isEnglish.value ? 'en-US' : 'zh-CN',
          review_focus: selectedIntentId.value,
        }),
      },
    )
    cases.value = [activeCase.value, ...cases.value.filter((item) => item.id !== activeCase.value?.id)]
    request.value = ''
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '评审运行失败'
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  const [historyResult, capabilityResult] = await Promise.allSettled([
    api<ReviewCase[]>('/review-agent/cases'),
    loadCapabilities(),
  ])
  if (historyResult.status === 'fulfilled') {
    const history = historyResult.value
    cases.value = history
  }
  if (capabilityResult.status === 'rejected') {
    error.value = isEnglish.value
      ? 'The reviewer is temporarily unavailable. Please try again later.'
      : '评审能力暂时不可用，请稍后重试。'
  } else if (historyResult.status === 'rejected') {
    error.value = isEnglish.value
      ? 'Review history is temporarily unavailable. You can still start a new review.'
      : '历史评审暂时无法读取，你仍可直接发起新评审。'
  }
})
</script>

<template>
  <AppShell
    :title="isEnglish ? 'Independent review' : '独立评审'"
    :eyebrow="isEnglish ? 'Upload · Converse · Decide' : '上传作品 · 对话评审 · 自主决策'"
  >
    <section class="standalone-review">
      <main class="review-stage">
        <div v-if="cases.length" class="review-toolbar">
          <button class="secondary history-trigger" type="button" @click="historyOpen = true">
            {{ isEnglish ? 'Review history' : '历史评审' }}
            <span>{{ cases.length }}</span>
          </button>
        </div>

        <section v-if="!activeCase" class="upload-panel">
          <p class="eyebrow">AgentScope · Reviewer</p>
          <h2>{{ isEnglish ? 'Review a work without creating a project.' : '不创建项目，直接评审一部作品。' }}</h2>
          <p>{{ isEnglish ? 'Upload a novel, screenplay, or story outline. The reviewer keeps the source unchanged and grounds every finding in evidence.' : '上传小说、剧本或故事大纲。评审 Agent 不改原稿，每项判断都应回到原文证据。' }}</p>
          <div class="review-fields">
            <label>{{ isEnglish ? 'Review domain' : '评审领域' }}
              <select v-model="reviewDomain" @change="changeDomain">
                <option value="novel">{{ isEnglish ? 'Novel' : '小说' }}</option>
                <option value="script">{{ isEnglish ? 'Screenplay' : '剧本' }}</option>
              </select>
            </label>
            <label>{{ isEnglish ? 'Document type' : '文档类型' }}
              <select v-model="documentKind">
                <option :value="reviewDomain">{{ reviewDomain === 'novel' ? (isEnglish ? 'Novel' : '小说') : (isEnglish ? 'Screenplay' : '剧本') }}</option>
                <option value="outline">{{ isEnglish ? 'Story outline' : '故事大纲' }}</option>
              </select>
            </label>
            <label>{{ isEnglish ? 'Title' : '作品名称' }}<input v-model="title" /></label>
            <label class="file-field">{{ isEnglish ? 'Source file' : '上传原稿' }}
              <input type="file" accept=".docx,.pdf,.txt,.md,.html" @change="pickFile" />
              <span>{{ uploadFile?.name || (isEnglish ? 'DOCX, PDF, TXT, MD or HTML' : '支持 DOCX、PDF、TXT、MD、HTML') }}</span>
            </label>
          </div>
          <button class="primary create-review" type="button" :disabled="!canCreate" @click="createCase">
            {{ busy ? (isEnglish ? 'Reading source…' : '正在读取原稿…') : (isEnglish ? 'Create review conversation' : '建立评审会话') }}
          </button>
        </section>

        <template v-else>
          <header class="case-header">
            <div><p class="eyebrow">{{ activeCase.source_filename }}</p><h2>{{ activeCase.title }}</h2></div>
            <button class="secondary" type="button" @click="activeCase = undefined">{{ isEnglish ? 'New review' : '新建评审' }}</button>
          </header>
          <section class="case-source" :aria-label="isEnglish ? 'Evidence source' : '证据来源'">
            <div>
              <small>{{ isEnglish ? 'Evidence source' : '证据来源' }}</small>
              <strong>{{ activeCase.source_filename }}</strong>
            </div>
            <p>
              {{
                isEnglish
                  ? 'This conversation is grounded in the uploaded manuscript. New review turns attach matched source evidence to the relevant response.'
                  : '本评审会话以该上传原稿为证据基础；后续评审会把命中的原文证据附在对应回复下。'
              }}
            </p>
          </section>
          <section class="case-conversation" aria-live="polite">
            <div v-if="!activeCase.messages.length" class="review-empty">
              <strong>{{ isEnglish ? 'The source is ready.' : '原稿已就绪。' }}</strong>
              <span>{{ isEnglish ? 'State the decision, scope, and evidence standard you need.' : '请说明需要判断的问题、评审范围和证据标准。' }}</span>
            </div>
            <article
              v-for="message in activeCase.messages"
              :key="message.id"
              :class="['case-message', `is-${message.actor}`]"
            >
              <small>{{ message.actor === 'user' ? (isEnglish ? 'You' : '你') : (isEnglish ? 'Reviewer' : '评审 Agent') }}</small>
              <AgentMessage v-if="message.actor === 'assistant'" :text="message.content" />
              <p v-else>{{ message.content }}</p>
              <details
                v-if="message.actor === 'assistant' && evidenceManifest(message).length"
                class="evidence-details"
              >
                <summary>
                  {{ isEnglish ? 'Source evidence' : '原文证据' }}
                  <span>{{ evidenceManifest(message).length }}</span>
                </summary>
                <ol>
                  <li v-for="evidence in evidenceManifest(message)" :key="evidence.evidence_id">
                    <strong>{{ evidence.evidence_id }}</strong>
                    <p>{{ evidence.preview }}</p>
                  </li>
                </ol>
              </details>
            </article>
            <div v-if="busy" class="review-running">{{ isEnglish ? 'Reviewer is reading evidence and preparing findings…' : '评审 Agent 正在核查证据并整理发现…' }}</div>
          </section>
          <form class="case-composer" @submit.prevent="send">
            <div
              class="review-intents"
              role="group"
              :aria-label="isEnglish ? 'Choose a review focus' : '选择评审重点'"
            >
              <button
                v-for="intent in reviewIntents"
                :key="intent.id"
                type="button"
                :class="{ active: selectedIntentId === intent.id }"
                :aria-pressed="selectedIntentId === intent.id"
                @click="selectedIntentId = intent.id"
              >
                {{ intent.label }}
              </button>
            </div>
            <p class="intent-help">{{ selectedIntent.instruction }}</p>
            <div class="composer-row">
              <textarea
                v-model="request"
                :aria-label="isEnglish ? 'Optional review details' : '可选的评审补充说明'"
                :placeholder="isEnglish
                  ? 'Add a specific question, scope, or evidence standard (optional)'
                  : '补充具体问题、评审范围或证据标准（可选）'"
              />
              <button class="primary" type="submit" :disabled="!canSend">
                {{
                  busy
                    ? (isEnglish ? 'Reviewing…' : '评审中…')
                    : canResume || hasConversation
                      ? (isEnglish ? 'Continue review' : '继续评审')
                      : (isEnglish ? 'Send' : '发起评审')
                }}
              </button>
            </div>
          </form>
        </template>
        <p v-if="error" class="error" role="alert">{{ error }}</p>

        <button
          v-if="historyOpen"
          class="drawer-backdrop"
          type="button"
          :aria-label="isEnglish ? 'Close review history' : '关闭历史评审'"
          @click="historyOpen = false"
        />
        <aside v-if="historyOpen" class="case-drawer" :aria-label="isEnglish ? 'Review history' : '历史评审'">
          <header>
            <div>
              <p class="eyebrow">Review cases</p>
              <h2>{{ isEnglish ? 'Review history' : '历史评审' }}</h2>
            </div>
            <button class="drawer-close" type="button" @click="historyOpen = false">
              {{ isEnglish ? 'Close' : '关闭' }}
            </button>
          </header>
          <div class="case-list">
            <button
              v-for="item in cases"
              :key="item.id"
              type="button"
              :class="{ active: activeCase?.id === item.id }"
              @click="openCase(item.id)"
            >
              <strong>{{ item.title }}</strong>
              <span>{{ item.document_kind }} · {{ item.review_domain }}</span>
            </button>
          </div>
        </aside>
      </main>
    </section>
  </AppShell>
</template>

<style scoped>
.standalone-review{min-height:720px;border:1px solid var(--line);border-radius:24px;overflow:hidden;background:var(--surface)}
.review-stage{min-width:0;min-height:720px;display:grid;grid-template-rows:auto 1fr auto auto;position:relative}.review-toolbar{display:flex;justify-content:flex-end;padding:18px 22px 0}.history-trigger{display:inline-flex;align-items:center;gap:9px}.history-trigger span{display:grid;place-items:center;min-width:24px;height:24px;padding:0 7px;border-radius:999px;background:var(--soft);color:var(--text);font-size:.75rem}.upload-panel{max-width:840px;align-self:center;justify-self:center;padding:42px 52px 64px;width:100%}.upload-panel h2{font-family:var(--font-display);font-size:2.35rem;line-height:1.14;margin:10px 0}.upload-panel>p{color:var(--muted);line-height:1.65}
.review-fields{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:28px 0}.review-fields label{display:grid;gap:7px;font-weight:700}.review-fields input,.review-fields select{width:100%;min-height:46px;border:1px solid var(--line);border-radius:12px;background:var(--surface);color:var(--text);padding:10px 12px}.file-field{grid-column:1/-1}.file-field input{padding:8px}.file-field span{color:var(--muted);font-size:.78rem;font-weight:400}.create-review{justify-self:start}
.case-header{display:flex;align-items:center;justify-content:space-between;padding:22px 26px 14px}.case-header h2{margin:4px 0 0}.case-source{display:grid;grid-template-columns:minmax(190px,.7fr) minmax(0,1.3fr);gap:20px;margin:0 24px 2px;padding:13px 15px;border:1px solid var(--line);border-radius:14px;background:var(--soft)}.case-source div{display:grid;gap:4px;min-width:0}.case-source small{color:var(--accent);font-weight:700}.case-source strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.case-source p{margin:0;color:var(--muted);font-size:.8rem;line-height:1.55}.case-conversation{padding:20px 24px 24px;overflow:auto;display:flex;flex-direction:column;gap:14px}.case-message{max-width:84%;padding:16px 18px;border:1px solid var(--line);border-radius:17px;line-height:1.7;overflow-wrap:anywhere}.case-message small{display:block;color:var(--accent);margin-bottom:8px}.case-message p{margin:0;white-space:pre-wrap}.case-message.is-user{align-self:flex-end;background:var(--soft)}.case-message.is-assistant{align-self:flex-start;background:var(--surface)}.review-running{align-self:flex-start;color:var(--muted);padding:12px 16px;border-radius:14px;background:var(--soft)}.review-empty{align-self:center;text-align:center;display:grid;gap:7px;color:var(--muted)}
.evidence-details{margin-top:14px;border-top:1px solid var(--line);padding-top:10px}.evidence-details summary{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:.78rem;cursor:pointer}.evidence-details summary span{display:grid;place-items:center;min-width:20px;height:20px;border-radius:999px;background:var(--soft);color:var(--text)}.evidence-details ol{display:grid;gap:9px;margin:12px 0 0;padding-left:22px}.evidence-details li{padding-left:4px}.evidence-details li strong{color:var(--accent);font-size:.75rem}.evidence-details li p{margin-top:3px;color:var(--muted);font-size:.78rem;line-height:1.55}
.case-composer{display:grid;gap:12px;padding:16px 24px 22px;border-top:1px solid var(--line)}.review-intents{display:flex;flex-wrap:wrap;gap:8px}.review-intents button{display:inline-flex;align-items:center;gap:7px;flex:0 0 auto;border:1px solid var(--line);border-radius:10px;background:var(--surface);color:var(--muted);padding:9px 14px;font:inherit;font-size:.82rem;cursor:pointer;transition:background .18s ease,border-color .18s ease,color .18s ease,box-shadow .18s ease,transform .18s ease}.review-intents button:hover{border-color:var(--accent);color:var(--text);transform:translateY(-1px)}.review-intents button:focus-visible{outline:3px solid color-mix(in srgb,var(--accent) 36%,transparent);outline-offset:2px}.review-intents button.active{border-color:var(--accent);background:var(--accent);color:#fffaf2;box-shadow:0 7px 18px color-mix(in srgb,var(--accent) 26%,transparent);font-weight:700}.review-intents button.active::before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor;box-shadow:0 0 0 3px color-mix(in srgb,currentColor 18%,transparent)}.review-intents button.active:hover{color:#fffaf2;filter:brightness(1.06)}.composer-row{display:grid;grid-template-columns:1fr auto;gap:12px}.case-composer textarea{min-height:96px;border:1px solid var(--line);border-radius:16px;background:var(--surface);color:var(--text);padding:14px;resize:vertical}.composer-row button{align-self:end}
.intent-help{margin:-2px 2px 0;color:var(--muted);font-size:.78rem;line-height:1.5}
.drawer-backdrop{position:absolute;inset:0;z-index:10;border:0;border-radius:0;background:color-mix(in srgb,#000 34%,transparent);cursor:default}.case-drawer{position:absolute;z-index:11;inset:0 0 0 auto;width:min(390px,92%);padding:24px;background:var(--surface);border-left:1px solid var(--line);box-shadow:-24px 0 70px color-mix(in srgb,#000 18%,transparent);overflow:auto}.case-drawer>header{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;margin-bottom:20px}.case-drawer h2{margin:4px 0 0}.drawer-close{border:1px solid var(--line);border-radius:999px;background:var(--surface);color:var(--text);padding:8px 12px}.case-list{display:grid;gap:10px}.case-list>button{text-align:left;display:grid;gap:6px;padding:15px;border:1px solid var(--line);border-radius:14px;background:var(--surface);color:var(--text)}.case-list>button:hover,.case-list>button.active{border-color:var(--accent);background:var(--soft)}.case-list span{color:var(--muted);font-size:.75rem}
.error{margin:0 24px 20px}
@media(max-width:900px){.review-fields{grid-template-columns:1fr}.upload-panel{padding:28px}.case-source{grid-template-columns:1fr}.case-message{max-width:100%}.review-toolbar{padding:14px 14px 0}.composer-row{grid-template-columns:1fr}.composer-row button{justify-self:end}}
</style>
