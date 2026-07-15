<!--
  SourcePanel — Workspace side panel listing a project's uploaded documents
  and letting the writer search/upload more.

  The panel polls every 3s while any source is still parsing/indexing so
  status flips to "已就绪" without a manual refresh. Search is on-demand.
-->
<template>
  <div class="src-panel">
    <div class="src-head">
      <span class="src-title">📚 参考资料</span>
      <span class="src-count" v-if="sources.length">{{ sources.length }}</span>
    </div>

    <div v-if="!sources.length" class="src-empty">
      <div class="src-empty-icon">📄</div>
      <div class="src-empty-title">还没有参考资料</div>
      <div class="src-empty-desc">上传小说 / 剧本 / 大纲后，Agent 可随时检索片段作参考</div>
    </div>

    <div v-else class="src-list">
      <div v-for="s in sources" :key="s.id" class="src-item">
        <div class="src-row">
          <span class="src-icon">📄</span>
          <span class="src-name" :title="s.filename">{{ s.filename }}</span>
          <span :class="['src-badge', s.status]">{{ statusLabel(s.status) }}</span>
          <button class="src-x" @click="handleDelete(s)" title="删除">✕</button>
        </div>
        <div class="src-meta" v-if="s.status === 'done'">
          {{ s.chunk_count }} 片段 · {{ Math.round(s.total_chars / 1000) }}k 字
        </div>
        <div class="src-summary" v-if="s.summary && s.status === 'done'" :title="s.summary">
          {{ s.summary.slice(0, 120) }}{{ s.summary.length > 120 ? '…' : '' }}
        </div>
        <div class="src-error" v-if="s.status === 'failed'">失败：{{ s.error || '未知错误' }}</div>
      </div>
    </div>

    <div class="src-search" v-if="sources.some(s => s.status === 'done')">
      <input
        v-model="query"
        placeholder="在参考资料中检索…"
        @keydown.enter="runSearch"
      />
      <button class="btn-p sm" @click="runSearch" :disabled="!query.trim() || searching">
        {{ searching ? '…' : '搜索' }}
      </button>
    </div>
    <div v-if="results.length" class="src-hits">
      <div v-for="h in results" :key="h.chunk_id" class="src-hit">
        <div class="hit-head">
          <span class="hit-file">{{ h.filename }}</span>
          <span class="hit-score">相关度 {{ h.score }}</span>
        </div>
        <div class="hit-preview">{{ h.preview }}</div>
      </div>
    </div>

    <div class="src-uploader">
      <FileUploader v-model="pendingFiles" :multiple="true" hint="拖入文件或点击选择" />
      <button
        v-if="pendingFiles.length"
        class="btn-p sm full"
        :disabled="uploading"
        @click="doUpload"
      >{{ uploading ? '上传中…' : `上传 ${pendingFiles.length} 个文件` }}</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import FileUploader from './FileUploader.vue'
import { listSources, deleteSource, uploadSource, searchSources } from '../api'

const props = defineProps<{ projectId: number; kind?: string }>()

const sources = ref<any[]>([])
const pendingFiles = ref<File[]>([])
const uploading = ref(false)

const query = ref('')
const results = ref<any[]>([])
const searching = ref(false)

let pollTimer: number | null = null

async function refresh() {
  try {
    const { data } = await listSources(props.projectId)
    sources.value = data
  } catch { /* ignore */ }
}

function schedulePolling() {
  if (pollTimer) return
  pollTimer = window.setInterval(async () => {
    const hasInflight = sources.value.some(
      s => s.status === 'pending' || s.status === 'parsing' || s.status === 'indexing',
    )
    if (!hasInflight) {
      if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
      return
    }
    await refresh()
  }, 3000)
}

async function doUpload() {
  if (!pendingFiles.value.length || uploading.value) return
  uploading.value = true
  try {
    for (const f of pendingFiles.value) {
      await uploadSource(props.projectId, f, props.kind || 'adaptation')
    }
    pendingFiles.value = []
    await refresh()
    schedulePolling()
  } catch (e: any) {
    window.alert(e?.response?.data?.detail || '上传失败')
  } finally {
    uploading.value = false
  }
}

async function handleDelete(s: any) {
  if (!confirm(`删除「${s.filename}」？`)) return
  try {
    await deleteSource(props.projectId, s.id)
    await refresh()
  } catch { /* ignore */ }
}

async function runSearch() {
  if (!query.value.trim()) return
  searching.value = true
  try {
    const { data } = await searchSources(props.projectId, query.value.trim(), 5)
    results.value = data
  } finally {
    searching.value = false
  }
}

function statusLabel(s: string) {
  return ({
    pending: '排队中',
    parsing: '解析中',
    indexing: '索引中',
    done: '已就绪',
    failed: '失败',
  } as any)[s] || s
}

onMounted(async () => {
  await refresh()
  schedulePolling()
})

onBeforeUnmount(() => {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
})
</script>

<style scoped>
.src-panel { display: flex; flex-direction: column; gap: 10px }
.src-head { display: flex; align-items: center; gap: 6px; padding-bottom: 4px }
.src-title { font-size: 13px; font-weight: 590; color: var(--t1) }
.src-count { font-size: 11px; color: var(--t4); background: var(--bg-surface); padding: 1px 6px; border-radius: 8px }

.src-empty { padding: 24px 0; text-align: center }
.src-empty-icon { font-size: 24px; opacity: .4; margin-bottom: 6px }
.src-empty-title { font-size: 12px; font-weight: 590; color: var(--t2) }
.src-empty-desc { font-size: 11px; color: var(--t5); line-height: 1.6; padding: 0 20px }

.src-list { display: flex; flex-direction: column; gap: 6px }
.src-item { background: var(--bg-surface); border: 1px solid var(--bs); border-radius: var(--r-md); padding: 8px 10px }
.src-row { display: flex; align-items: center; gap: 6px }
.src-icon { flex-shrink: 0 }
.src-name { flex: 1; font-size: 12px; color: var(--t1); overflow: hidden; text-overflow: ellipsis; white-space: nowrap }
.src-badge { font-size: 10px; padding: 1px 6px; border-radius: 4px }
.src-badge.pending, .src-badge.parsing, .src-badge.indexing { background: rgba(255,180,60,0.12); color: #ffb43c }
.src-badge.done { background: rgba(80,200,120,0.14); color: #50c878 }
.src-badge.failed { background: rgba(220,50,50,0.14); color: #ff8080 }
.src-x { background: none; border: none; color: var(--t5); cursor: pointer; padding: 0 4px }
.src-x:hover { color: var(--red) }
.src-meta { font-size: 10px; color: var(--t5); margin-top: 4px }
.src-summary { font-size: 11px; color: var(--t3); line-height: 1.5; margin-top: 4px; max-height: 3em; overflow: hidden }
.src-error { font-size: 11px; color: #ff8080; margin-top: 4px }

.src-search { display: flex; gap: 6px }
.src-search input { flex: 1; background: rgba(255,255,255,0.03); border: 1px solid var(--bs); border-radius: var(--r-md); padding: 6px 10px; color: var(--t1); font-size: 12px; outline: none }
.src-search input:focus { border-color: var(--accent) }

.src-hits { display: flex; flex-direction: column; gap: 4px }
.src-hit { background: var(--bg-surface); border-left: 2px solid var(--accent); padding: 6px 8px; border-radius: 4px }
.hit-head { display: flex; justify-content: space-between; font-size: 10px; color: var(--t4); margin-bottom: 4px }
.hit-preview { font-size: 11px; color: var(--t2); line-height: 1.5 }

.src-uploader { display: flex; flex-direction: column; gap: 6px }
.btn-p.sm { padding: 4px 10px; font-size: 12px }
.btn-p.full { width: 100% }
</style>
