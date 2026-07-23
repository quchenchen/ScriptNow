<script setup lang="ts">
type Manuscript = {
  unit_type: 'chapter' | 'scene'
  ordinal: number
  title: string
  adopted_content: string
  status: string
  candidate: null | {
    status?: string
    content: string
    state_delta: Record<string, Record<string, unknown>>
    thread_actions: Array<{ action: string; note: string }>
    continuity_report: Array<{ check: string; status: string; message: string; excerpt?: string }>
  }
}

const props = defineProps<{
  manuscript: Manuscript
  novel: boolean
  busy: boolean
  documentContent: string
  metadata: Record<string, string | string[]>
  saveStatus: 'idle' | 'dirty' | 'saving' | 'saved' | 'failed' | 'conflict'
  versions?: Array<{ version: number; content: string; source: string; metadata?: Record<string, string | string[]> }>
  currentVersion?: number
}>()
const emit = defineEmits<{
  selectText: [event: Event]
  updateDocument: [content: string]
  updateMetadata: [metadata: Record<string, string | string[]>]
  adopt: []
  generateNext: []
  restoreVersion: [version: number]
  regenerate: []
}>()

function updateMetadata(key: string, value: string) {
  emit('updateMetadata', {
    ...props.metadata,
    [key]: key === 'characters' ? value.split(/[、,，]/).map(item => item.trim()).filter(Boolean) : value,
  })
}
</script>

<template>
  <div class="draft-head">
    <div><span class="kicker">{{ manuscript.status === 'adopted' ? '已采用 · 已进入正文' : '候选正文 · 尚未写入作品' }}</span><h1>{{ manuscript.title }}</h1></div>
    <span class="health stable">连续性检查完成</span>
  </div>
  <section v-if="manuscript.status === 'adopted'" class="manuscript-metadata" :aria-label="novel ? '章节叙述信息' : '场景信息'">
    <template v-if="novel">
      <label>视角人物<input :value="metadata.pov_character" placeholder="本章跟随谁" @input="updateMetadata('pov_character', ($event.target as HTMLInputElement).value)" /></label>
      <label>叙述人称<select :value="metadata.narrative_person" @change="updateMetadata('narrative_person', ($event.target as HTMLSelectElement).value)"><option>第一人称</option><option>第三人称</option><option>全知视角</option></select></label>
      <label>时间位置<input :value="metadata.time_position" placeholder="例如：上一章三小时后" @input="updateMetadata('time_position', ($event.target as HTMLInputElement).value)" /></label>
    </template>
    <template v-else>
      <label>场景头<select :value="metadata.scene_heading" @change="updateMetadata('scene_heading', ($event.target as HTMLSelectElement).value)"><option>内景</option><option>外景</option><option>内外景</option></select></label>
      <label>地点<input :value="metadata.location" placeholder="主要地点" @input="updateMetadata('location', ($event.target as HTMLInputElement).value)" /></label>
      <label>时间<input :value="metadata.time_of_day" placeholder="日 / 夜 / 清晨" @input="updateMetadata('time_of_day', ($event.target as HTMLInputElement).value)" /></label>
      <label>出场人物<input :value="Array.isArray(metadata.characters) ? metadata.characters.join('、') : metadata.characters" placeholder="用顿号分隔" @input="updateMetadata('characters', ($event.target as HTMLInputElement).value)" /></label>
    </template>
  </section>
  <textarea
    v-if="manuscript.status === 'adopted'"
    class="manuscript manuscript-editor"
    :value="documentContent"
    :aria-label="`已采用${novel ? '章节' : '场次'}正文`"
    @input="$emit('updateDocument', ($event.target as HTMLTextAreaElement).value)"
    @select="$emit('selectText', $event)"
    @mouseup="$emit('selectText', $event)"
    @keyup="$emit('selectText', $event)"
  />
  <div v-if="manuscript.status === 'adopted'" :class="['editor-save-state', saveStatus]" aria-live="polite">
    {{ saveStatus === 'dirty' ? '有未保存修改' : saveStatus === 'saving' ? '正在保存…' : saveStatus === 'saved' ? '已保存' : saveStatus === 'failed' ? '保存失败，将保留当前内容' : saveStatus === 'conflict' ? '正文已在其他位置更新，请重新比较' : '正文已载入' }}
  </div>
  <details v-if="manuscript.status === 'adopted' && versions?.length" class="document-history">
    <summary>正文历史 · 当前 v{{ currentVersion }}</summary>
    <article v-for="item in versions" :key="item.version">
      <div><b>v{{ item.version }}</b><small>{{ item.source === 'adopted_baseline' ? '采用基线' : item.source === 'manual_edit' ? '人工编辑' : item.source.startsWith('restore_') ? '历史恢复' : 'AI 修改' }}</small></div>
      <button :disabled="item.version === currentVersion" @click="$emit('restoreVersion', item.version)">{{ item.version === currentVersion ? '当前版本' : '恢复为新版本' }}</button>
    </article>
  </details>
  <div v-else-if="manuscript.candidate" class="manuscript">{{ manuscript.candidate.content }}</div>
  <div v-if="manuscript.candidate?.status === 'stale'" class="stale-candidate"><b>故事资料已经变化</b><span>这个旧候选不会再被采用。重新生成会创建同一{{novel?'章':'场'}}的 Revision Task，并要求 Agent 提供新事实的正文证据。</span></div>
  <slot name="revision" />
  <details v-if="manuscript.candidate && manuscript.status !== 'adopted'" class="change-preview compact-impact">
    <summary>查看采用影响与连续性检查</summary>
    <b>采用后将发生</b>
    <div v-for="(delta, name) in manuscript.candidate.state_delta" :key="name"><span>{{ name }}</span><small>{{ delta }}</small></div>
    <div v-for="action in manuscript.candidate.thread_actions" :key="action.note"><span>伏笔 · {{ action.action }}</span><small>{{ action.note }}</small></div>
    <div class="checks"><span v-for="check in manuscript.candidate.continuity_report" :key="`${check.check}-${check.message}`" :class="check.status">{{check.status==='blocking'?'!':'✓'}} {{ check.message }}<small v-if="check.excerpt">证据 · {{check.excerpt}}</small></span></div>
  </details>
  <button v-if="manuscript.status !== 'adopted' && manuscript.candidate?.status !== 'stale'" class="primary" :disabled="busy" @click="$emit('adopt')">{{ busy ? '正在写入作品事实…' : '采用正文并更新叙事状态' }}</button>
  <button v-else-if="manuscript.candidate?.status === 'stale'" class="primary" :disabled="busy" @click="$emit('regenerate')">{{busy?'Agent 正在按最新资料修订…':`按最新故事资料修订本${novel?'章':'场'}`}}</button>
  <div v-else class="truth manuscript-next"><span>正文已采用并进入后续创作上下文</span><button class="primary" :disabled="busy" @click="$emit('generateNext')">{{ busy ? '写作者正在准备…' : `生成第 ${manuscript.ordinal + 1} ${novel ? '章' : '场'}候选` }}</button></div>
</template>
