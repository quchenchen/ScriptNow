<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { api } from '../api'

const props = withDefaults(defineProps<{
  projectId: string
  initialMode?: 'export' | 'history'
  showToolbar?: boolean
}>(), { showToolbar: true })
const emit = defineEmits<{ close: [] }>()
interface ChapterOption { id: string; title: string; status: string; selectable: boolean }
interface ExportOptions { volumes: Array<{ id: string; title: string; selection: string; chapters: ChapterOption[] }> }
interface Snapshot { id: string; version: number; name: string; scope: string[]; word_count: number; content_hash: string; created_at: string }
interface Diff { current_hash: string; units: Array<{ unit_id: string; status: string; lines: string[] }> }
const mode = ref<'export' | 'history'>()
const options = ref<ExportOptions>({ volumes: [] })
const router = useRouter()
const selected = ref<string[]>([])
const form = ref<'clean' | 'working'>('clean')
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
  try {
    if (next === 'export') {
      options.value = await api(`/novel/projects/${props.projectId}/exports/options`)
      selected.value = options.value.volumes.flatMap((volume) => volume.chapters.filter((chapter) => chapter.selectable).map((chapter) => chapter.id))
    } else await loadSnapshots()
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : next === 'export' ? '加载导出选项失败' : '加载历史版本失败'
  }
}
function close() {
  mode.value = undefined
  emit('close')
}
function toggle(id: string) { selected.value = selected.value.includes(id) ? selected.value.filter((item) => item !== id) : [...selected.value, id] }
async function generateExport() {
  busy.value = true
  try {
    const manifest = await api<{ id: string }>(`/novel/projects/${props.projectId}/exports`, { method: 'POST', body: JSON.stringify({ chapter_ids: selected.value, form: form.value, idempotency_key: crypto.randomUUID() }) })
    const link = document.createElement('a'); link.href = `/api/novel/projects/${props.projectId}/exports/${manifest.id}/download`; link.click()
  } catch (caught) { error.value = caught instanceof Error ? caught.message : '导出失败' }
  finally { busy.value = false }
}
async function generatePackagedExport() {
  busy.value = true
  try {
    const csrf = document.cookie.split('; ').find(row => row.startsWith('sf_csrf='))?.split('=')[1] ?? ''
    const resp = await fetch(`/api/novel/projects/${props.projectId}/exports/packaged`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
      body: JSON.stringify({ chapter_ids: selected.value, idempotency_key: crypto.randomUUID() }),
    })
    if (!resp.ok) throw new Error('打包导出失败')
    const blob = await resp.blob()
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = 'novel-packaged.docx'
    link.click()
    URL.revokeObjectURL(link.href)
  } catch (caught) { error.value = caught instanceof Error ? caught.message : '打包导出失败' }
  finally { busy.value = false }
}
async function loadSnapshots() { snapshots.value = await api(`/novel/projects/${props.projectId}/snapshots`) }
async function saveSnapshot() {
  if (!snapshotName.value.trim()) return
  busy.value = true
  try { await api(`/novel/projects/${props.projectId}/snapshots`, { method: 'POST', body: JSON.stringify({ name: snapshotName.value }) }); snapshotName.value = ''; await loadSnapshots() }
  catch (caught) { error.value = caught instanceof Error ? caught.message : '保存版本失败' }
  finally { busy.value = false }
}
async function inspect(snapshot: Snapshot) { activeSnapshot.value = snapshot; preview.value = await api(`/novel/projects/${props.projectId}/snapshots/${snapshot.id}/diff`) }
async function rollback() {
  if (!activeSnapshot.value || !preview.value) return
  busy.value = true
  try { await api(`/novel/projects/${props.projectId}/snapshots/${activeSnapshot.value.id}/rollback`, { method: 'POST', body: JSON.stringify({ expected_current_hash: preview.value.current_hash, idempotency_key: crypto.randomUUID() }) }); mode.value = undefined; window.dispatchEvent(new CustomEvent('scriptnow:document-changed')) }
  catch (caught) { error.value = caught instanceof Error ? caught.message : '回滚失败，请重新对比' }
  finally { busy.value = false }
}
onMounted(() => {
  if (props.initialMode) void open(props.initialMode)
})
</script>

<template>
  <div v-if="showToolbar" class="delivery-toolbar"><span>Novel · {{ selectedCount ? `${selectedCount} 章已就绪` : '交付工具' }}</span><button @click="router.push('/')">回到控制台</button><button @click="open('history')">历史版本</button><button class="primary" @click="open('export')">导出小说</button></div>
  <div v-if="mode" class="delivery-backdrop" @click.self="close"><section class="delivery-modal"><header><div><p class="eyebrow">Novel Delivery</p><h2>{{ mode === 'export' ? '导出小说' : '历史版本' }}</h2></div><button aria-label="关闭" @click="close">×</button></header><p v-if="error" class="error">{{ error }}</p>
    <template v-if="mode === 'export'"><div class="scope-tree"><article v-for="volume in options.volumes" :key="volume.id"><h3>{{ volume.title }} <small>{{ volume.selection === 'partial' ? '部分完稿' : volume.selection }}</small></h3><label v-for="chapter in volume.chapters" :key="chapter.id" :class="{ disabled: !chapter.selectable }"><input type="checkbox" :checked="selected.includes(chapter.id)" :disabled="!chapter.selectable" @change="toggle(chapter.id)" /><span>{{ chapter.title }}</span><em>{{ chapter.status === 'done' ? '完稿' : '无稿件' }}</em></label></article></div><fieldset><legend>交付形态</legend><label><input v-model="form" type="radio" value="clean" />纯净稿</label><label><input v-model="form" type="radio" value="working" />工作稿</label></fieldset><footer><span>已选 {{ selectedCount }} 章</span><button class="primary" :disabled="busy || !selectedCount" @click="generateExport">{{ busy ? '生成中…' : '生成 DOCX' }}</button><button class="primary" :disabled="busy || !selectedCount" @click="generatePackagedExport" style="margin-top:8px">{{ busy ? '生成中…' : '📦 打包导出（含封面+简介）' }}</button></footer></template>
    <template v-else><form class="snapshot-form" @submit.prevent="saveSnapshot"><input v-model="snapshotName" maxlength="160" placeholder="为当前稿命名" required /><button class="primary" :disabled="busy">保存当前版本</button></form><div class="snapshot-list"><button v-for="snapshot in snapshots" :key="snapshot.id" :class="{ active: activeSnapshot?.id === snapshot.id }" @click="inspect(snapshot)"><strong>v{{ snapshot.version }} · {{ snapshot.name }}</strong><small>{{ snapshot.scope.length }} 章 · {{ snapshot.word_count }} 字 · {{ new Date(snapshot.created_at).toLocaleString() }}</small></button></div><div v-if="preview" class="snapshot-diff"><h3>相对当前稿</h3><article v-for="unit in preview.units" :key="unit.unit_id"><strong>{{ unit.unit_id }} · {{ unit.status }}</strong><pre>{{ unit.lines.join('\n') }}</pre></article><button class="secondary danger" :disabled="busy" @click="rollback">回滚为新修订版本</button></div></template>
  </section></div>
</template>
