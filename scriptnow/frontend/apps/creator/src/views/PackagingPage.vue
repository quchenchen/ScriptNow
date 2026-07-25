<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '../api'
import { pickCreativeCopy } from '../creativeCopy'
import AppShell from '../components/AppShell.vue'
import { useLayoutStore } from '../stores/layout'

interface OutputSpec { key: string; platform: string; width: number; height: number; ratio: string; formats: string[]; max_bytes: number | null; note: string; default: boolean }
interface ImageModel { id: string; display_name: string; provider_name: string; available: boolean; reason: string | null }
interface WorkPackage { id: string; version: number; title: string; synopsis: string; tags: string[]; language: string; cover_brief: Record<string, unknown>; cover_prompt: string }
interface Cover { id: string; image_url: string; platform_key: string; width: number; height: number; language: string; status: string }

const route = useRoute()
const router = useRouter()
const layout = useLayoutStore()
const projectId = computed(() => String(route.params.projectId))
const specs = ref<OutputSpec[]>([])
const models = ref<ImageModel[]>([])
const selected = ref<string[]>([])
const selectedModel = ref('')
const workPackage = ref<WorkPackage | null>(null)
const coverPrompt = ref('')
const covers = ref<Cover[]>([])
const feedback = ref('')
const busy = ref<'package' | 'cover' | ''>('')
const packagingVision = pickCreativeCopy('packaging')
const elapsedSeconds = ref(0)
let elapsedTimer: number | undefined
const error = ref('')
const needsDirection = ref(false)
const generationStatus = computed(() => {
  if (busy.value === 'package') return {
    title: '包装 Agent 正在提炼作品',
    detail: '正在读取已采纳的创作方向与蓝图，生成书名、简介、标签和封面视觉指令。',
  }
  if (busy.value === 'cover') return {
    title: `正在生成 ${selected.value.length} 种封面`,
    detail: 'image2 正在按所选平台规格逐张生成，完成后会在本页展示结果。',
  }
  return null
})

function startProgress() {
  elapsedSeconds.value = 0
  if (elapsedTimer) window.clearInterval(elapsedTimer)
  elapsedTimer = window.setInterval(() => { elapsedSeconds.value += 1 }, 1000)
}
function stopProgress() {
  if (elapsedTimer) window.clearInterval(elapsedTimer)
  elapsedTimer = undefined
}

function presentError(reason: unknown, fallback: string): string {
  const message = reason instanceof Error ? reason.message : fallback
  if (message.includes('adopted creative direction') || message.includes('采纳一个创作方向')) {
    needsDirection.value = true
    return '生成作品包装前，需要先从创意方案中选定一个方向。'
  }
  needsDirection.value = false
  return message
}
async function goToIdeation() {
  layout.setStudioView('ideation')
  await router.push(`/projects/${projectId.value}`)
}

async function load() {
  error.value = ''
  try {
    const [availableSpecs, availableModels, existing, existingCovers] = await Promise.all([
      api<OutputSpec[]>(`/projects/${projectId.value}/packaging/cover-output-specs`),
      api<ImageModel[]>(`/projects/${projectId.value}/packaging/image-models`),
      api<WorkPackage | null>(`/projects/${projectId.value}/packaging`),
      api<Cover[]>(`/projects/${projectId.value}/packaging/covers`),
    ])
    specs.value = availableSpecs
    models.value = availableModels
    selected.value = availableSpecs.filter((item) => item.default).map((item) => item.key)
    selectedModel.value = availableModels.find((item) => item.available)?.id ?? ''
    workPackage.value = existing
    coverPrompt.value = existing?.cover_prompt ?? ''
    covers.value = existingCovers ?? []
  } catch (reason) { error.value = presentError(reason, '加载作品包装失败') }
}
function toggle(key: string) {
  selected.value = selected.value.includes(key) ? selected.value.filter((item) => item !== key) : [...selected.value, key]
}
async function generatePackage() {
  busy.value = 'package'; error.value = ''
  startProgress()
  try {
    const generated = await api<WorkPackage>(`/projects/${projectId.value}/packaging/generate`, {
      method: 'POST', body: JSON.stringify({ idempotency_key: crypto.randomUUID(), feedback: feedback.value || null }),
    })
    workPackage.value = generated
    coverPrompt.value = generated.cover_prompt
  } catch (reason) { error.value = presentError(reason, '包装 Agent 生成失败') }
  finally { busy.value = ''; stopProgress() }
}
async function generateCovers() {
  if (!selected.value.length || !selectedModel.value) return
  busy.value = 'cover'; error.value = ''
  startProgress()
  try {
    covers.value = await api(`/projects/${projectId.value}/packaging/covers/generate`, {
      method: 'POST', body: JSON.stringify({ image_model_id: selectedModel.value, output_keys: selected.value, prompt: coverPrompt.value }),
    })
  } catch (reason) { error.value = presentError(reason, '封面生成失败') }
  finally { busy.value = ''; stopProgress() }
}
onMounted(() => void load())
onUnmounted(stopProgress)
</script>

<template>
  <AppShell title="作品包装" eyebrow="书名 · 简介 · 标签 · 封面">
    <section class="package-lead"><div><h2>{{ packagingVision }}</h2><p>包装 Agent 会读取已采纳的方向与蓝图，生成书名、约 200 词简介、标签和封面视觉简报。</p></div><button class="primary" :disabled="Boolean(busy)" @click="generatePackage">{{ busy === 'package' ? '正在提炼…' : workPackage ? '根据反馈重新提炼' : '生成作品包装' }}</button></section>
    <section v-if="generationStatus" class="generation-status" role="status" aria-live="polite"><span class="status-spinner" aria-hidden="true" /><div><strong>{{ generationStatus.title }}</strong><p>{{ generationStatus.detail }}</p></div><time>{{ elapsedSeconds }} 秒</time></section>
    <section v-if="error" class="package-error" :class="{ actionable: needsDirection }"><div><strong>{{ needsDirection ? '还差一步' : '暂时无法继续' }}</strong><p>{{ error }}</p></div><button v-if="needsDirection" @click="goToIdeation">前往创意发散</button></section>
    <section v-if="workPackage" class="package-copy"><header><span>第 {{ workPackage.version }} 版 · {{ workPackage.language }}</span><h2>{{ workPackage.title }}</h2></header><p>{{ workPackage.synopsis }}</p><div><span v-for="tag in workPackage.tags" :key="tag">{{ tag }}</span></div><label>调整意见<textarea v-model="feedback" placeholder="例如：更突出禁忌关系，弱化类型套路感。" /></label></section>
    <section v-if="workPackage" class="prompt-editor"><header><div><p class="eyebrow">封面 Prompt</p><h2>Agent 提炼的视觉指令</h2><p>可在生成前直接调整。最终使用版本会随封面保存，不会覆盖 Agent 原稿。</p></div><button :disabled="coverPrompt === workPackage.cover_prompt" @click="coverPrompt = workPackage.cover_prompt">恢复 Agent 原稿</button></header><textarea v-model="coverPrompt" maxlength="20000" spellcheck="false" /><footer><span :class="{ changed: coverPrompt !== workPackage.cover_prompt }">{{ coverPrompt === workPackage.cover_prompt ? '当前为 Agent 原稿' : '已由用户调整' }}</span><small>{{ coverPrompt.length }} / 20,000</small></footer></section>
    <section class="cover-config"><header><div><p class="eyebrow">输出尺寸</p><h2>选择需要生成的平台规格</h2><p>默认生成 Wattpad 高清版和 Webnovel 严格版，可自由单选或多选。</p></div></header>
      <div class="spec-grid"><button v-for="spec in specs" :key="spec.key" :class="{ selected: selected.includes(spec.key) }" @click="toggle(spec.key)"><span>{{ selected.includes(spec.key) ? '✓' : '' }}</span><strong>{{ spec.platform }}</strong><b>{{ spec.width }} × {{ spec.height }} px</b><small>{{ spec.ratio }} · {{ spec.formats.join('/') }}</small><p>{{ spec.note }}</p></button></div>
      <div class="cover-actions"><label>生图模型<select v-model="selectedModel" :disabled="Boolean(busy)"><option value="" disabled>选择可用模型</option><option v-for="model in models" :key="model.id" :value="model.id" :disabled="!model.available" data-i18n-skip>{{ model.display_name }} · {{ model.provider_name }}{{ model.available ? '' : '（不可用）' }}</option></select></label><button class="primary" :disabled="!workPackage || !selected.length || !selectedModel || Boolean(busy)" @click="generateCovers">{{ busy === 'cover' ? `正在生成 ${selected.length} 种封面…` : `生成 ${selected.length} 种封面` }}</button></div>
    </section>
    <section v-if="covers.length" class="cover-results"><article v-for="cover in covers" :key="cover.id"><img :src="cover.image_url" :alt="`${cover.width} × ${cover.height} 封面候选`" /><strong>{{ specs.find((item) => item.key === cover.platform_key)?.platform }}</strong><small>{{ cover.width }} × {{ cover.height }} · {{ cover.language }}</small></article></section>
  </AppShell>
</template>

<style scoped>
.package-lead,.cover-actions{display:flex;justify-content:space-between;gap:24px;align-items:center}.package-lead,.package-copy,.prompt-editor,.cover-config{border:1px solid #ded7c9;border-radius:18px;background:#fffdf9;padding:24px;margin-bottom:20px}.package-lead h2,.prompt-editor h2,.cover-config h2{font-family:Georgia,serif;font-size:28px;margin:0 0 8px}.package-lead p,.prompt-editor p,.cover-config p{color:#6d685f;margin:0}.generation-status{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:16px;margin-bottom:20px;padding:16px 20px;border:1px solid #a9c0b7;border-radius:12px;background:#edf4ef;color:#183f32}.generation-status strong{display:block;margin-bottom:4px}.generation-status p{margin:0;color:#536b62}.generation-status time{font-variant-numeric:tabular-nums;color:#536b62}.status-spinner{width:22px;height:22px;border:3px solid #bdd0c7;border-top-color:#1f4b3d;border-radius:50%;animation:status-spin .9s linear infinite}@keyframes status-spin{to{transform:rotate(360deg)}}.package-error{display:flex;justify-content:space-between;align-items:center;gap:20px;background:#fff0ed;color:#8d3729;padding:16px 20px;border-radius:12px;margin-bottom:20px}.package-error strong{display:block;margin-bottom:4px}.package-error p{margin:0}.package-error.actionable{background:#fff8e8;color:#65491d;border:1px solid #ead7a4}.package-error button{border:0;border-radius:9px;background:#ad4c27;color:white;padding:10px 15px;font-weight:700;white-space:nowrap}.package-copy header span{color:#a64c29;font-size:13px}.package-copy h2{font-family:Georgia,serif;font-size:36px;margin:8px 0}.package-copy>p{font-size:16px;line-height:1.8;max-width:860px}.package-copy>div{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}.package-copy>div span{background:#edf2eb;border-radius:999px;padding:6px 10px}.package-copy label{display:grid;gap:8px}.package-copy textarea{min-height:72px;padding:12px;border:1px solid #d7cdbd;border-radius:10px}.prompt-editor header{display:flex;justify-content:space-between;gap:20px;align-items:start}.prompt-editor header button{border:1px solid #cfc5b6;border-radius:9px;background:white;padding:9px 12px}.prompt-editor textarea{box-sizing:border-box;width:100%;min-height:210px;margin-top:18px;padding:16px;border:1px solid #cfc5b6;border-radius:12px;background:#f8f7f2;font:14px/1.65 ui-monospace,SFMono-Regular,Menlo,monospace;resize:vertical}.prompt-editor footer{display:flex;justify-content:space-between;margin-top:8px;color:#777}.prompt-editor footer .changed{color:#a64c29;font-weight:700}.spec-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:20px 0}.spec-grid button{text-align:left;display:grid;gap:7px;border:1px solid #d9d2c5;border-radius:14px;background:#faf8f2;padding:16px;min-height:190px}.spec-grid button.selected{border:2px solid #1f4b3d;background:#edf4ef}.spec-grid button>span{height:18px;color:#1f4b3d}.spec-grid b{font-size:20px}.spec-grid small{color:#a24c2a}.spec-grid p{font-size:13px;line-height:1.5}.cover-actions label{display:grid;gap:6px}.cover-actions select{min-width:280px;padding:11px;border:1px solid #d7cdbd;border-radius:9px;background:white}.primary{border:0;border-radius:10px;background:#ad4c27;color:white;padding:12px 20px;font-weight:700}.primary:disabled{opacity:.45}.cover-results{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,300px));gap:18px}.cover-results article{display:grid;gap:6px}.cover-results img{width:100%;aspect-ratio:2/3;object-fit:cover;border-radius:12px;background:#eee}.cover-results small{color:#777}@media(max-width:720px){.package-lead,.cover-actions,.prompt-editor header,.package-error{align-items:stretch;flex-direction:column}.generation-status{grid-template-columns:auto 1fr}.generation-status time{grid-column:2}.cover-actions select{min-width:0;width:100%}}
</style>
