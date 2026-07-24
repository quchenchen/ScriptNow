<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useLocale } from '@scriptnow/shared'

import { api, ApiError } from '../api'
import type { WorkspaceFile } from '../types'

const props = defineProps<{ projectId: string }>()
const { isEnglish } = useLocale()
const ui = (zh: string, en: string) => isEnglish.value ? en : zh

interface DistillationSummary {
  id: string
  status: string
  pass_key: string
  checkpoint: { processed_chunk_ids?: string[] }
  coverage: { total_chunks?: number; evidence_count?: number; gaps?: string[] }
}
interface SourceEvidence {
  id: string
  source_unit: string
  dimension: string
  claim: string
  confidence: number
  inference: boolean
}
interface SourceCandidate {
  id: string
  version: number
  decision: string
  profile: Record<string, unknown>
  conflicts: Array<Record<string, unknown>>
  exclusions: string[]
  evidence: SourceEvidence[]
}
interface DistillationDetail extends DistillationSummary { candidate: SourceCandidate | null }
interface Preflight {
  provider_key: string | null
  model_key: string | null
  runtime_connected: boolean
  consent_version: string
  purpose: string[]
  sources: Array<{ id: string; name: string; byte_size: number }>
  processed_chunks: number
  total_chunks: number
}
interface RunState { status: string; error_code?: string | null }

const distillation = ref<DistillationDetail | null>(null)
const preflight = ref<Preflight | null>(null)
const runId = ref('')
const consent = ref(false)
const feedback = ref('')
const busy = ref(false)
const error = ref('')
let timer: number | undefined

const processed = computed(() => distillation.value?.checkpoint.processed_chunk_ids?.length ?? 0)
const total = computed(() => distillation.value?.coverage.total_chunks ?? preflight.value?.total_chunks ?? 0)
const progress = computed(() => total.value ? Math.round(processed.value / total.value * 100) : 0)
const candidate = computed(() => distillation.value?.candidate ?? null)
const profileRows = computed(() => Object.entries(candidate.value?.profile ?? {}))

const passLabels: Record<string, [string, string]> = {
  inventory: ['整理素材', 'Preparing sources'],
  atomic_evidence: ['提取逐段证据', 'Extracting passage evidence'],
  cross_unit_synthesis: ['跨章节综合', 'Synthesizing across chapters'],
  conflict_gap_analysis: ['检查矛盾与缺口', 'Checking conflicts and gaps'],
  candidate_profile: ['形成候选画像', 'Building the candidate profile'],
  human_decision: ['等待你的审查', 'Waiting for your review'],
}
const statusLabels: Record<string, [string, string]> = {
  pending: ['等待开始', 'Waiting to start'],
  running: ['分析中', 'Analyzing'],
  ready: ['已完成', 'Complete'],
  ready_with_gaps: ['已完成，存在待确认项', 'Complete with items to review'],
  failed: ['已中断，可从检查点继续', 'Stopped; ready to resume'],
  cancelled: ['已取消', 'Cancelled'],
}
const profileLabels: Record<string, [string, string]> = {
  narrative_voice: ['叙述声音', 'Narrative voice'],
  character_strategy: ['人物策略', 'Character strategy'],
  relationship_dynamics: ['关系动力', 'Relationship dynamics'],
  world_rules: ['世界规则', 'World rules'],
  plot_patterns: ['情节策略', 'Plot strategy'],
  emotional_promises: ['情感承诺', 'Emotional promises'],
  quality_constraints: ['质量边界', 'Quality boundaries'],
}

function labelFor(table: Record<string, [string, string]>, key: string): string {
  const labels = table[key]
  return labels ? ui(labels[0], labels[1]) : key.replaceAll('_', ' ')
}

function explain(value: unknown): string {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.map(explain).join(' · ')
  return JSON.stringify(value, null, 2)
}

async function loadLatest() {
  const latest = await api<DistillationSummary | null>(`/projects/${props.projectId}/source-distillations/latest`)
  if (!latest) return
  distillation.value = await api<DistillationDetail>(`/projects/${props.projectId}/source-distillations/${latest.id}`)
}

async function prepare() {
  busy.value = true
  error.value = ''
  try {
    if (!distillation.value) {
      const files = await api<WorkspaceFile[]>(`/projects/${props.projectId}/files`)
      const ready = files.filter((item) => item.status === 'ready')
      if (!ready.length) throw new Error(ui('请先上传并完成素材索引。', 'Upload and index source material first.'))
      distillation.value = await api<DistillationDetail>(`/projects/${props.projectId}/source-distillations`, {
        method: 'POST',
        body: JSON.stringify({
          source_file_ids: ready.map((item) => item.id),
          idempotency_key: `source-profile-${Date.now()}`,
        }),
      })
    }
    preflight.value = await api<Preflight>(`/projects/${props.projectId}/source-distillations/${distillation.value.id}/execution-preflight`)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : ui('暂时无法准备来源分析。', 'Unable to prepare source analysis.')
  } finally {
    busy.value = false
  }
}

async function execute() {
  if (!preflight.value || !consent.value || !distillation.value) return
  busy.value = true
  error.value = ''
  try {
    const response = await api<{ run_id: string }>(`/projects/${props.projectId}/source-distillations/${distillation.value.id}/execute`, {
      method: 'POST',
      body: JSON.stringify({
        idempotency_key: `source-analysis-${Date.now()}`,
        external_processing_consent: true,
        consent_version: preflight.value.consent_version,
      }),
    })
    runId.value = response.run_id
    preflight.value = null
    consent.value = false
    await poll()
  } catch (cause) {
    error.value = cause instanceof ApiError ? cause.message : ui('无法启动来源分析。', 'Unable to start source analysis.')
    busy.value = false
  }
}

async function poll() {
  if (!distillation.value) return
  try {
    distillation.value = await api<DistillationDetail>(`/projects/${props.projectId}/source-distillations/${distillation.value.id}`)
    const terminal = ['ready', 'ready_with_gaps', 'failed', 'cancelled'].includes(distillation.value.status)
    if (runId.value) {
      const run = await api<RunState>(`/runs/${runId.value}`)
      if (run.status === 'failed' || run.status === 'cancelled') {
        error.value = ui('分析已中断，检查点已保留，可重新启动。', 'Analysis stopped. Its checkpoint is preserved for retry.')
        busy.value = false
        return
      }
    }
    if (terminal || candidate.value) {
      busy.value = false
      return
    }
    timer = window.setTimeout(poll, 1800)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : ui('无法读取分析进度。', 'Unable to read analysis progress.')
    busy.value = false
  }
}

async function decide(approve: boolean) {
  if (!candidate.value || !distillation.value) return
  busy.value = true
  error.value = ''
  try {
    await api(`/projects/${props.projectId}/source-profiles/${candidate.value.id}/decision`, {
      method: 'POST',
      body: JSON.stringify({ approve, feedback: feedback.value.trim() || null }),
    })
    await loadLatest()
    feedback.value = ''
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : ui('无法保存你的决定。', 'Unable to save your decision.')
  } finally {
    busy.value = false
  }
}

onMounted(() => { loadLatest().catch(() => undefined) })
onUnmounted(() => { if (timer) window.clearTimeout(timer) })
</script>

<template>
  <section class="source-profile-panel" aria-labelledby="source-profile-title">
    <header>
      <div><p class="eyebrow">{{ ui('来源画像', 'Source profile') }}</p><h3 id="source-profile-title">{{ ui('让参考素材成为可审查的创作依据', 'Turn source material into reviewable creative evidence') }}</h3></div>
      <span v-if="candidate" class="candidate-state">v{{ candidate.version }} · {{ candidate.decision }}</span>
    </header>
    <p>{{ ui('系统会分批提取证据、跨章综合并检查冲突；只有你批准的画像才会进入后续创作上下文。', 'The system extracts cited evidence in batches, synthesizes across units, and checks conflicts. Only an approved profile enters future writing context.') }}</p>
    <p v-if="error" class="source-profile-error">{{ error }}</p>

    <div v-if="distillation && !candidate" class="source-profile-progress">
      <div><strong>{{ ui('分析进度', 'Analysis progress') }}</strong><span>{{ processed }} / {{ total }} · {{ progress }}%</span></div>
      <progress :value="processed" :max="total || 1" />
      <small>{{ labelFor(passLabels, distillation.pass_key) }} · {{ labelFor(statusLabels, distillation.status) }}</small>
    </div>

    <div v-if="preflight" class="source-consent-card">
      <h4>{{ ui('确认第三方模型处理', 'Confirm third-party model processing') }}</h4>
      <dl><div><dt>{{ ui('模型服务商', 'Model provider') }}</dt><dd>{{ preflight.provider_key || '—' }}</dd></div><div><dt>{{ ui('模型', 'Model') }}</dt><dd>{{ preflight.model_key || '—' }}</dd></div><div><dt>{{ ui('范围', 'Scope') }}</dt><dd>{{ preflight.sources.map((item) => item.name).join('、') }}</dd></div><div><dt>{{ ui('用途', 'Purpose') }}</dt><dd>{{ preflight.purpose.join('、') }}</dd></div></dl>
      <label class="source-consent"><input v-model="consent" type="checkbox" />{{ ui('我确认将上述素材分批发送到该第三方 Provider，仅用于本项目的来源分析。', 'I authorize sending these source excerpts to this third-party Provider solely for this project’s source analysis.') }}</label>
      <div class="source-profile-actions"><button class="secondary" @click="preflight = null">{{ ui('取消', 'Cancel') }}</button><button :disabled="!consent || !preflight.runtime_connected || busy" @click="execute">{{ ui('授权并开始', 'Authorize and start') }}</button></div>
      <small v-if="!preflight.runtime_connected">{{ ui('Reviewer Agent 的真实模型尚未连接。', 'The Reviewer Agent model is not connected.') }}</small>
    </div>

    <template v-if="candidate">
      <div class="source-profile-grid"><article v-for="([key, value]) in profileRows" :key="key"><small>{{ labelFor(profileLabels, key) }}</small><p>{{ explain(value) }}</p></article></div>
      <details v-if="candidate.evidence.length"><summary>{{ ui(`查看 ${candidate.evidence.length} 条引用证据`, `Review ${candidate.evidence.length} cited evidence items`) }}</summary><ol class="source-evidence-list"><li v-for="item in candidate.evidence" :key="item.id"><span>{{ item.dimension }} · {{ item.confidence }}%</span><p>{{ item.claim }}</p><small>{{ item.source_unit }}{{ item.inference ? ` · ${ui('推断', 'inferred')}` : '' }}</small></li></ol></details>
      <div v-if="candidate.decision === 'candidate'" class="source-decision"><label>{{ ui('审查意见（可选）', 'Review note (optional)') }}<textarea v-model="feedback" :placeholder="ui('指出需要保留、修订或排除的内容', 'State what to preserve, revise, or exclude')" /></label><div class="source-profile-actions"><button class="secondary" :disabled="busy" @click="decide(false)">{{ ui('驳回并保留旧版本', 'Reject and keep prior version') }}</button><button :disabled="busy" @click="decide(true)">{{ ui('批准进入创作上下文', 'Approve for writing context') }}</button></div></div>
    </template>

    <button v-else-if="!preflight" class="secondary source-profile-start" :disabled="busy" @click="prepare">{{ busy ? ui('正在读取…', 'Loading…') : distillation ? ui('从检查点继续', 'Resume from checkpoint') : ui('分析参考素材', 'Analyze source material') }}</button>
  </section>
</template>
