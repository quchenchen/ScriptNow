<!--
  CreateProjectWizard — a 3-step creation flow.

  Step 1 · Source mode  — how the story starts
                          (original pitch/synopsis/theme, adaption, rewrite)
  Step 2 · Basics       — title, type, audience, background, genre, style
  Step 3 · Seed         — seed_content (textarea) OR file upload (adaption/rewrite)

  The wizard owns state internally and emits ``done`` with the final project
  once creation + optional upload complete. Parent is responsible for closing
  the overlay + navigating.
-->
<template>
  <div class="wizard">
    <div class="wz-head">
      <h3>新建项目</h3>
      <div class="wz-steps">
        <div v-for="s in [1,2,3]" :key="s" :class="['wz-step', { active: step === s, done: step > s }]">
          <span class="wz-num">{{ s }}</span>
          <span class="wz-lbl">{{ stepLabel(s) }}</span>
        </div>
      </div>
    </div>

    <!-- Step 1 · 来源模式 ─────────────────────────────────── -->
    <section v-if="step === 1" class="wz-body">
      <p class="wz-intro">告诉 Agent 你想从哪里开始 — 灵感、大纲、主题、还是要改编 / 改写一部现成的作品？</p>
      <div class="mode-grid">
        <label v-for="m in modes" :key="m.key" :class="['mode-card', { on: form.source_mode === m.key }]">
          <input type="radio" v-model="form.source_mode" :value="m.key" />
          <span class="mode-icon">{{ m.icon }}</span>
          <span class="mode-title">{{ m.title }}</span>
          <span class="mode-desc">{{ m.desc }}</span>
        </label>
      </div>
    </section>

    <!-- Step 2 · 基本信息 ─────────────────────────────────── -->
    <section v-if="step === 2" class="wz-body">
      <div class="form-row">
        <label>标题</label>
        <input v-model="form.title" placeholder="给你的项目起个名字" autofocus />
      </div>
      <div class="form-row">
        <label>创作类型</label>
        <div class="radio-group">
          <label class="radio" :class="{sel: form.type==='novel'}">
            <input type="radio" v-model="form.type" value="novel" /> 📖 小说
          </label>
          <label class="radio" :class="{sel: form.type==='script'}">
            <input type="radio" v-model="form.type" value="script" /> 🎬 剧本
          </label>
          <label class="radio" :class="{sel: form.type==='video_prompt'}">
            <input type="radio" v-model="form.type" value="video_prompt" /> 🎥 视频提示词
          </label>
        </div>
      </div>
      <div class="form-row row-2">
        <div>
          <label>目标受众</label>
          <select v-model="form.target_audience">
            <option value="男频">男频</option>
            <option value="女频">女频</option>
            <option value="通用">通用</option>
          </select>
        </div>
        <div>
          <label>文化背景</label>
          <select v-model="form.cultural_background">
            <option value="国内">国内</option>
            <option value="海外">海外</option>
          </select>
        </div>
      </div>
      <div class="form-row">
        <label>题材类型 <span class="hint">（可多选）</span></label>
        <div class="chips">
          <span
            v-for="g in genreOptions"
            :key="g"
            :class="['chip', { on: selectedGenres.includes(g) }]"
            @click="toggleGenre(g)"
          >{{ g }}</span>
        </div>
      </div>
      <div class="form-row">
        <label>叙事风格 <span class="hint">（单选，可留空）</span></label>
        <div class="chips">
          <span
            v-for="s in styleOptions"
            :key="s"
            :class="['chip', { on: form.style_preference === s }]"
            @click="form.style_preference = form.style_preference === s ? '' : s"
          >{{ s }}</span>
        </div>
      </div>
    </section>

    <!-- Step 3 · 种子内容 / 文档 ─────────────────────────── -->
    <section v-if="step === 3" class="wz-body">
      <template v-if="needsUpload">
        <div class="form-row">
          <label>{{ form.source_mode === 'adapted' ? '原著标题' : '原剧本 / 原文标题' }}</label>
          <input v-model="form.original_work" placeholder="例：《巷子里的诗人》" />
        </div>
        <div class="form-row">
          <label>参考文档</label>
          <FileUploader v-model="uploadFiles" />
          <p class="wz-note">
            上传后 Agent 会自动分块建索引，创作时可随时检索原文片段作为参考。
          </p>
        </div>
      </template>
      <template v-else>
        <div class="form-row">
          <label>{{ seedLabel }}</label>
          <textarea
            v-model="form.seed_content"
            :placeholder="seedPlaceholder"
            rows="8"
          ></textarea>
          <p class="wz-note">{{ seedHint }}</p>
        </div>
      </template>
    </section>

    <div class="wz-error" v-if="error">{{ error }}</div>

    <footer class="wz-actions">
      <button class="btn" @click="cancel" :disabled="busy">取消</button>
      <span class="spacer"></span>
      <button v-if="step > 1" class="btn" @click="step--" :disabled="busy">上一步</button>
      <button v-if="step < 3" class="btn-p" @click="next" :disabled="!canNext">下一步</button>
      <button v-else class="btn-p" @click="submit" :disabled="!canSubmit || busy">
        {{ busy ? busyLabel : '创建项目' }}
      </button>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import FileUploader from './FileUploader.vue'
import { createProject, uploadSource } from '../api'
import { genreOptions, styleOptions } from '../constants/creative'

const emit = defineEmits<{ (e: 'done', p: any): void; (e: 'cancel'): void }>()

const step = ref(1)
const error = ref('')
const busy = ref(false)
const busyLabel = ref('创建中…')

const form = reactive({
  source_mode: 'original_pitch',
  title: '',
  type: 'script',
  target_audience: '男频',
  cultural_background: '国内',
  style_preference: '',
  seed_content: '',
  original_work: '',
})

const selectedGenres = ref<string[]>([])
const uploadFiles = ref<File[]>([])

const modes = [
  { key: 'original_pitch',    icon: '💡', title: '原创 · 一句话灵感',
    desc: '一两句核心创意，让 Agent 帮你展开' },
  { key: 'original_synopsis', icon: '📝', title: '原创 · 梗概',
    desc: '已经想好故事线，让 Agent 帮你架构' },
  { key: 'original_theme',    icon: '🎯', title: '原创 · 只给主题',
    desc: '只有主题或题材方向，从头共创' },
  { key: 'adapted',           icon: '📚', title: '改编',
    desc: '基于一部现成小说 / 原著' },
  { key: 'rewrite',           icon: '✂️', title: '改写',
    desc: '基于一部现成剧本，换调性或结构' },
]

const needsUpload = computed(() =>
  form.source_mode === 'adapted' || form.source_mode === 'rewrite',
)

const seedLabel = computed(() => ({
  original_pitch: '你的核心灵感',
  original_synopsis: '故事梗概',
  original_theme: '主题 / 方向',
}[form.source_mode] ?? '内容'))

const seedPlaceholder = computed(() => ({
  original_pitch: '一句话把故事的核心冲突讲清楚，例：一个盲人侦探要抓住一个连环杀手。',
  original_synopsis: '写下你已有的故事大纲，段落之间空一行分隔。',
  original_theme: '例：讲一个关于「原谅」的故事，都市背景，冷色调基调。',
}[form.source_mode] ?? ''))

const seedHint = computed(() => ({
  original_pitch: 'Agent 会以此为起点，帮你扩写成完整方案。',
  original_synopsis: 'Agent 会基于梗概推导角色、场景与冲突。',
  original_theme: 'Agent 会先与你确认基调、再逐步构建故事。',
}[form.source_mode] ?? ''))

const canNext = computed(() => {
  if (step.value === 1) return !!form.source_mode
  if (step.value === 2) return form.title.trim().length > 0
  return true
})

const canSubmit = computed(() => {
  if (!form.title.trim()) return false
  if (needsUpload.value) return uploadFiles.value.length > 0
  return form.seed_content.trim().length > 0
})

function stepLabel(s: number) {
  return { 1: '来源', 2: '基本信息', 3: '种子' }[s] ?? ''
}

function toggleGenre(g: string) {
  const i = selectedGenres.value.indexOf(g)
  if (i >= 0) selectedGenres.value.splice(i, 1)
  else selectedGenres.value.push(g)
}

function next() {
  if (canNext.value) step.value++
}

function cancel() {
  if (busy.value) return
  emit('cancel')
}

async function submit() {
  if (!canSubmit.value || busy.value) return
  busy.value = true
  error.value = ''
  try {
    busyLabel.value = '创建中…'
    const payload = {
      title: form.title.trim(),
      type: form.type,
      genre: JSON.stringify(selectedGenres.value),
      target_audience: form.target_audience,
      cultural_background: form.cultural_background,
      style_preference: form.style_preference,
      source_mode: form.source_mode,
      seed_content: form.seed_content.trim(),
      original_work: form.original_work.trim(),
    }
    const { data: project } = await createProject(payload)

    if (needsUpload.value && uploadFiles.value.length) {
      for (let i = 0; i < uploadFiles.value.length; i++) {
        busyLabel.value = `上传 ${i + 1}/${uploadFiles.value.length}…`
        await uploadSource(project.id, uploadFiles.value[i], form.source_mode)
      }
    }

    emit('done', project)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || '创建失败，请重试'
  } finally {
    busy.value = false
    busyLabel.value = '创建中…'
  }
}
</script>

<style scoped>
.wizard { background: var(--bg-panel); border: 1px solid var(--bw); border-radius: 12px; width: 560px; max-width: 90vw; max-height: 88vh; overflow: hidden; display: flex; flex-direction: column }
.wz-head { padding: 20px 24px 12px; border-bottom: 1px solid var(--bs) }
.wz-head h3 { font-size: 16px; font-weight: 590; color: var(--t1); margin-bottom: 12px }
.wz-steps { display: flex; align-items: center; gap: 6px }
.wz-step { display: flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 20px; font-size: 12px; color: var(--t4); background: var(--bg-surface) }
.wz-step.active { color: var(--t1); background: var(--accent); font-weight: 590 }
.wz-step.done { color: var(--t2); background: var(--bg-active) }
.wz-num { width: 18px; height: 18px; border-radius: 50%; background: rgba(255,255,255,0.1); display: inline-flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 590 }
.wz-step.active .wz-num { background: rgba(255,255,255,0.25) }
.wz-lbl { font-size: 12px }

.wz-body { padding: 20px 24px; overflow-y: auto; flex: 1 }
.wz-intro { font-size: 13px; color: var(--t3); margin-bottom: 16px; line-height: 1.6 }

.mode-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px }
.mode-card { display: flex; flex-direction: column; gap: 4px; padding: 14px; border: 1px solid var(--bs); border-radius: var(--r-lg); background: var(--bg-surface); cursor: pointer; transition: all .12s }
.mode-card:hover { border-color: var(--bw); background: #1f1f23 }
.mode-card.on { border-color: var(--accent); background: rgba(88,166,255,0.06) }
.mode-card input { display: none }
.mode-icon { font-size: 22px }
.mode-title { font-size: 13px; font-weight: 590; color: var(--t1) }
.mode-desc { font-size: 11px; color: var(--t4); line-height: 1.4 }

.form-row { margin-bottom: 14px }
.form-row.row-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px }
.form-row label { display: block; font-size: 11px; color: var(--t4); text-transform: uppercase; letter-spacing: .04em; margin-bottom: 4px }
.form-row .hint { text-transform: none; letter-spacing: 0; color: var(--t5) }
.form-row input, .form-row select, .form-row textarea { width: 100%; background: rgba(255,255,255,0.03); border: 1px solid var(--bs); border-radius: var(--r-md); padding: 8px 10px; color: var(--t1); font-size: 13px; outline: none; font-family: inherit }
.form-row textarea { resize: vertical; line-height: 1.6 }
.form-row input:focus, .form-row select:focus, .form-row textarea:focus { border-color: var(--accent) }
.radio-group { display: flex; gap: 12px }
.radio { display: flex; align-items: center; gap: 4px; font-size: 13px; color: var(--t2); cursor: pointer; padding: 4px 8px; border-radius: var(--r-md) }
.radio.sel { background: rgba(88,166,255,0.1); color: var(--t1) }
.chips { display: flex; flex-wrap: wrap; gap: 6px }
.chip { padding: 4px 10px; background: var(--bg-surface); border: 1px solid var(--bs); border-radius: 16px; font-size: 12px; color: var(--t3); cursor: pointer; transition: all .12s }
.chip:hover { border-color: var(--bw); color: var(--t1) }
.chip.on { background: var(--accent); border-color: var(--accent); color: white }
.wz-note { font-size: 11px; color: var(--t5); margin-top: 6px; line-height: 1.5 }

.wz-error { padding: 10px 24px; background: rgba(220,50,50,0.1); color: #ff9090; font-size: 12px; border-top: 1px solid rgba(220,50,50,0.3) }

.wz-actions { display: flex; align-items: center; gap: 8px; padding: 14px 24px; border-top: 1px solid var(--bs); background: var(--bg-panel) }
.wz-actions .spacer { flex: 1 }
</style>
