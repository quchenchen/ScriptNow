<!--
  FileUploader — drag/drop or click to select one or more documents.

  Emits pure File objects. Parent decides when + how to upload; keeping the
  network call out of this component means it's reusable both in the create
  wizard (upload right after project create) and in Workspace (upload later).
-->
<template>
  <div
    class="uploader"
    :class="{ dragging: isDragging }"
    @dragenter.prevent="isDragging = true"
    @dragover.prevent="isDragging = true"
    @dragleave.prevent="isDragging = false"
    @drop.prevent="onDrop"
    @click="triggerInput"
  >
    <input
      ref="fileInput"
      type="file"
      :multiple="multiple"
      :accept="accept"
      style="display:none"
      @change="onPick"
    />
    <div v-if="!files.length" class="drop-empty">
      <div class="drop-icon">📎</div>
      <div class="drop-title">拖拽文件到这里 或 点击选择</div>
      <div class="drop-hint">{{ hint }}</div>
    </div>
    <div v-else class="file-list">
      <div v-for="(f, i) in files" :key="i" class="file-row">
        <span class="file-icon">📄</span>
        <span class="file-name">{{ f.name }}</span>
        <span class="file-size">{{ fmtSize(f.size) }}</span>
        <button class="file-x" @click.stop="remove(i)" title="移除">✕</button>
      </div>
      <div class="drop-more" @click.stop="triggerInput">+ 继续添加</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  multiple?: boolean
  accept?: string
  hint?: string
  modelValue?: File[]
  maxSizeMB?: number
}>(), {
  multiple: true,
  accept: '.txt,.md,.docx,.pdf',
  hint: '支持 .txt / .md / .docx / .pdf，单文件 ≤ 20MB',
  modelValue: () => [],
  maxSizeMB: 20,
})

const emit = defineEmits<{ (e: 'update:modelValue', v: File[]): void }>()

const fileInput = ref<HTMLInputElement | null>(null)
const isDragging = ref(false)
const files = ref<File[]>([...(props.modelValue ?? [])])

// Keep local mirror in sync if parent replaces the value externally
watch(() => props.modelValue, (v) => { files.value = [...(v ?? [])] })

function triggerInput() { fileInput.value?.click() }

function onPick(e: Event) {
  const t = e.target as HTMLInputElement
  if (t.files) addFiles(Array.from(t.files))
  t.value = ''  // allow re-selecting the same file
}

function onDrop(e: DragEvent) {
  isDragging.value = false
  const items = e.dataTransfer?.files
  if (items) addFiles(Array.from(items))
}

function addFiles(picked: File[]) {
  const maxBytes = props.maxSizeMB * 1024 * 1024
  const good: File[] = []
  for (const f of picked) {
    if (f.size > maxBytes) {
      window.alert(`「${f.name}」超过 ${props.maxSizeMB}MB，已跳过`)
      continue
    }
    good.push(f)
  }
  const next = props.multiple ? [...files.value, ...good] : good.slice(0, 1)
  files.value = next
  emit('update:modelValue', next)
}

function remove(i: number) {
  files.value.splice(i, 1)
  emit('update:modelValue', [...files.value])
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
}
</script>

<style scoped>
.uploader { border: 2px dashed var(--bs); border-radius: var(--r-lg); padding: 16px; cursor: pointer; transition: all .15s; background: rgba(255,255,255,0.02) }
.uploader:hover, .uploader.dragging { border-color: var(--accent); background: rgba(88,166,255,0.06) }
.drop-empty { display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 24px 0; color: var(--t3); text-align: center }
.drop-icon { font-size: 28px; opacity: .5 }
.drop-title { font-size: 13px; color: var(--t2); font-weight: 590 }
.drop-hint { font-size: 11px; color: var(--t4) }
.file-list { display: flex; flex-direction: column; gap: 6px }
.file-row { display: flex; align-items: center; gap: 8px; padding: 8px 10px; background: var(--bg-surface); border-radius: var(--r-md); font-size: 12px }
.file-icon { flex-shrink: 0 }
.file-name { flex: 1; color: var(--t1); overflow: hidden; text-overflow: ellipsis; white-space: nowrap }
.file-size { color: var(--t4); font-size: 11px }
.file-x { background: none; border: none; color: var(--t4); cursor: pointer; padding: 2px 6px; font-size: 12px }
.file-x:hover { color: var(--red) }
.drop-more { padding: 6px; text-align: center; color: var(--accent); font-size: 12px; cursor: pointer; border: 1px dashed var(--bs); border-radius: var(--r-md) }
.drop-more:hover { background: rgba(88,166,255,0.06) }
</style>
