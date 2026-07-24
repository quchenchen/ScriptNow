<script setup lang="ts">
import { computed, ref } from 'vue'

import { api } from '../api'
import TranslationOptions from './TranslationOptions.vue'

const props = defineProps<{ projectId: string }>()
interface SceneOption { id: string; title: string; status: string; selectable: boolean }
interface ExportOptions { creative_language?: string; episodes: Array<{ id: string; title: string; selection: string; scenes: SceneOption[] }> }
interface Snapshot { id: string; version: number; name: string; scope: string[]; word_count: number; content_hash: string; created_at: string }
interface Diff { current_hash: string; units: Array<{ unit_id: string; status: string; lines: string[] }> }

const mode = ref<'export' | 'history'>()
const options = ref<ExportOptions>({ episodes: [] })
const selected = ref<string[]>([])
const form = ref<'clean' | 'working'>('clean')
const translationMode = ref<'none' | 'faithful'>('none')
const targetLanguage = ref('')
const snapshots = ref<Snapshot[]>([])
const snapshotName = ref('')
const preview = ref<Diff>()
const activeSnapshot = ref<Snapshot>()
const busy = ref(false)
const error = ref('')
const selectedCount = computed(() => selected.value.length)

async function open(next: 'export' | 'history') {
  mode.value = next
  error.value = ''
  if (next === 'export') {
    options.value = await api(`/script/projects/${props.projectId}/exports/options`)
    selected.value = options.value.episodes.flatMap((episode) => episode.scenes.filter((scene) => scene.selectable).map((scene) => scene.id))
  } else await loadSnapshots()
}
function toggle(id: string) {
  selected.value = selected.value.includes(id) ? selected.value.filter((item) => item !== id) : [...selected.value, id]
}
async function generateExport() {
  busy.value = true
  try {
    const manifest = await api<{ id: string }>(`/script/projects/${props.projectId}/exports`, {
      method: 'POST', body: JSON.stringify({ scene_ids: selected.value, form: form.value, translation_mode: translationMode.value, target_language: translationMode.value === 'faithful' ? targetLanguage.value : null, idempotency_key: crypto.randomUUID() }),
    })
    const link = document.createElement('a')
    link.href = `/api/script/projects/${props.projectId}/exports/${manifest.id}/download`
    link.click()
  } catch (caught) { error.value = caught instanceof Error ? caught.message : '导出失败' }
  finally { busy.value = false }
}
async function loadSnapshots() {
  snapshots.value = await api(`/script/projects/${props.projectId}/snapshots`)
}
async function saveSnapshot() {
  if (!snapshotName.value.trim()) return
  busy.value = true
  try {
    await api(`/script/projects/${props.projectId}/snapshots`, { method: 'POST', body: JSON.stringify({ name: snapshotName.value }) })
    snapshotName.value = ''
    await loadSnapshots()
  } catch (caught) { error.value = caught instanceof Error ? caught.message : '保存版本失败' }
  finally { busy.value = false }
}
async function inspect(snapshot: Snapshot) {
  activeSnapshot.value = snapshot
  preview.value = await api(`/script/projects/${props.projectId}/snapshots/${snapshot.id}/diff`)
}
async function rollback() {
  if (!activeSnapshot.value || !preview.value) return
  busy.value = true
  try {
    await api(`/script/projects/${props.projectId}/snapshots/${activeSnapshot.value.id}/rollback`, {
      method: 'POST', body: JSON.stringify({ expected_current_hash: preview.value.current_hash, idempotency_key: crypto.randomUUID() }),
    })
    mode.value = undefined
    window.dispatchEvent(new CustomEvent('scriptnow:document-changed'))
  } catch (caught) { error.value = caught instanceof Error ? caught.message : '回滚失败，请重新对比' }
  finally { busy.value = false }
}
</script>

<template>
  <div class="delivery-toolbar"><span>Script · {{ selectedCount ? `${selectedCount} 场已就绪` : '交付工具' }}</span><button @click="open('history')">历史版本</button><button class="primary" @click="open('export')">导出剧本</button></div>
  <div v-if="mode" class="delivery-backdrop" @click.self="mode = undefined">
    <section class="delivery-modal">
      <header><div><p class="eyebrow">Script Delivery</p><h2>{{ mode === 'export' ? '导出剧本' : '历史版本' }}</h2></div><button aria-label="关闭" @click="mode = undefined">×</button></header>
      <p v-if="error" class="error">{{ error }}</p>
      <template v-if="mode === 'export'">
        <div class="scope-tree"><article v-for="episode in options.episodes" :key="episode.id"><h3>{{ episode.title }} <small>{{ episode.selection === 'partial' ? '部分完稿' : episode.selection }}</small></h3><label v-for="scene in episode.scenes" :key="scene.id" :class="{ disabled: !scene.selectable }"><input type="checkbox" :checked="selected.includes(scene.id)" :disabled="!scene.selectable" @change="toggle(scene.id)" /><span>{{ scene.title }}</span><em>{{ scene.status === 'done' ? '完稿' : '无稿件' }}</em></label></article></div>
        <fieldset><legend>交付形态</legend><label><input v-model="form" type="radio" value="clean" />纯净稿</label><label><input v-model="form" type="radio" value="working" />工作稿</label></fieldset>
        <TranslationOptions v-model:mode="translationMode" v-model:target-language="targetLanguage" :source-language="options.creative_language" />
        <footer><span>已选 {{ selectedCount }} 场</span><button class="primary" :disabled="busy || !selectedCount || (translationMode === 'faithful' && !targetLanguage)" @click="generateExport">{{ busy ? '生成中…' : translationMode === 'faithful' ? '翻译并生成 DOCX' : '生成 DOCX' }}</button></footer>
      </template>
      <template v-else>
        <form class="snapshot-form" @submit.prevent="saveSnapshot"><input v-model="snapshotName" maxlength="160" placeholder="为当前稿命名" required /><button class="primary" :disabled="busy">保存当前版本</button></form>
        <div class="snapshot-list"><button v-for="snapshot in snapshots" :key="snapshot.id" :class="{ active: activeSnapshot?.id === snapshot.id }" @click="inspect(snapshot)"><strong>v{{ snapshot.version }} · {{ snapshot.name }}</strong><small>{{ snapshot.scope.length }} 场 · {{ snapshot.word_count }} 字 · {{ new Date(snapshot.created_at).toLocaleString() }}</small></button></div>
        <div v-if="preview" class="snapshot-diff"><h3>相对当前稿</h3><article v-for="unit in preview.units" :key="unit.unit_id"><strong>{{ unit.unit_id }} · {{ unit.status }}</strong><pre>{{ unit.lines.join('\n') }}</pre></article><button class="secondary danger" :disabled="busy" @click="rollback">回滚为新修订版本</button></div>
      </template>
    </section>
  </div>
</template>
