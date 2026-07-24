<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useLocale } from '@scriptnow/shared'

import { api } from '../api'

type Verdict = 'pass' | 'revise' | 'block'
interface QualityDimension {
  dimension: string
  verdict: Verdict
  score: number
  evidence: string[]
  diagnosis: string
  repair: string
}
interface QualityReport {
  id: string
  revision_id: string
  rubric_version: string
  overall_status: 'ready' | 'revision_required' | 'blocked'
  maturity_score: number
  summary: string
  dimensions: QualityDimension[]
}

const props = defineProps<{ projectId: string; chapterId: string; revisionId: string }>()
const { isEnglish } = useLocale()
const reports = ref<QualityReport[]>([])
const busy = ref(false)
const error = ref('')
const current = computed(() => reports.value.find((item) => item.revision_id === props.revisionId))
const labels: Record<string, [string, string]> = {
  character_agency: ['人物能动性', 'Character agency'],
  scene_causality: ['场景因果', 'Scene causality'],
  relationship_progression: ['关系推进', 'Relationship progression'],
  narrative_voice: ['叙述声音', 'Narrative voice'],
  continuity: ['连续性', 'Continuity'],
  source_boundary: ['来源边界', 'Source boundary'],
  chapter_propulsion: ['章节推动力', 'Chapter propulsion'],
  prose_texture: ['语言质感', 'Prose texture'],
}
const label = (key: string) => labels[key]?.[isEnglish.value ? 1 : 0] ?? key
const verdictLabel = (value: Verdict) => ({
  pass: isEnglish.value ? 'Pass' : '通过',
  revise: isEnglish.value ? 'Revise' : '需修订',
  block: isEnglish.value ? 'Blocked' : '阻断',
}[value])

async function load() {
  if (!props.revisionId) return
  try {
    reports.value = await api<QualityReport[]>(
      `/novel/projects/${props.projectId}/chapters/${props.chapterId}/quality-reports`,
    )
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '质量报告读取失败'
  }
}
async function evaluate() {
  busy.value = true
  error.value = ''
  try {
    await api(
      `/novel/projects/${props.projectId}/chapters/${props.chapterId}/quality-reports/generate`,
      {
        method: 'POST',
        body: JSON.stringify({ revision_id: props.revisionId, idempotency_key: crypto.randomUUID() }),
      },
    )
    await load()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '质量评测未完成'
  } finally {
    busy.value = false
  }
}

watch(() => [props.projectId, props.chapterId, props.revisionId], load, { immediate: true })
</script>

<template>
  <section class="quality-panel">
    <header>
      <div><p class="eyebrow">{{ isEnglish ? 'Chapter maturity' : '章节成熟度' }}</p><h3>{{ current ? `${current.maturity_score}/100` : (isEnglish ? 'Not evaluated' : '尚未评测') }}</h3></div>
      <button class="secondary" :disabled="busy" @click="evaluate">{{ busy ? (isEnglish ? 'Reviewing…' : '审读中…') : current ? (isEnglish ? 'Re-evaluate' : '重新评测') : (isEnglish ? 'Evaluate' : '评测本稿') }}</button>
    </header>
    <p v-if="error" class="quality-error" role="alert">{{ error }}</p>
    <p v-if="!current" class="quality-empty">{{ isEnglish ? 'The report is bound to this exact revision and will not alter the candidate.' : '报告只绑定当前修订，不会改写或自动采纳候选稿。' }}</p>
    <template v-else>
      <p class="quality-summary" :class="current.overall_status">{{ current.summary }}</p>
      <details v-for="item in current.dimensions" :key="item.dimension" class="quality-axis" :class="item.verdict">
        <summary><strong>{{ label(item.dimension) }}</strong><span>{{ verdictLabel(item.verdict) }} · {{ item.score }}/5</span></summary>
        <div><p><b>{{ isEnglish ? 'Evidence' : '证据' }}</b></p><blockquote v-for="evidence in item.evidence" :key="evidence">{{ evidence }}</blockquote><p>{{ item.diagnosis }}</p><p><b>{{ isEnglish ? 'Revision direction' : '修订方向' }}</b> · {{ item.repair }}</p></div>
      </details>
    </template>
  </section>
</template>

<style scoped>
.quality-panel{display:grid;gap:12px}.quality-panel header{display:flex;align-items:center;justify-content:space-between;gap:12px}.quality-panel h3{margin:2px 0 0;font-family:Georgia,serif;font-size:24px}.quality-empty,.quality-summary,.quality-error{margin:0;padding:12px;border-radius:10px;background:#f3f0e9;line-height:1.55}.quality-error,.quality-summary.blocked{background:#fae7e1;color:#8f2f20}.quality-summary.ready{background:#e5f0e9;color:#234f3d}.quality-axis{border:1px solid #ded6c8;border-radius:10px;background:#fff}.quality-axis summary{display:flex;justify-content:space-between;gap:8px;padding:11px;cursor:pointer}.quality-axis summary span{font-size:12px;color:#766e63}.quality-axis.revise summary span{color:#a5552f}.quality-axis.block summary span{color:#a02f26}.quality-axis>div{padding:0 11px 11px;font-size:13px;line-height:1.5}.quality-axis p{margin:7px 0}.quality-axis blockquote{margin:7px 0;padding-left:9px;border-left:2px solid #c8bda9;color:#625b52}.eyebrow{margin:0;color:#a44d2d;font-size:11px;letter-spacing:.12em;text-transform:uppercase}
</style>
