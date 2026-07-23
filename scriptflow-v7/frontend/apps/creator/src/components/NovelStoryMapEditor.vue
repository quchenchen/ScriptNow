<script setup lang="ts">
import { ref } from 'vue'

import type { NovelState } from '../stores/novel'

type Volume = NovelState['story_map']['volumes'][number]
const props = defineProps<{ volumes: Volume[] }>()
const emit = defineEmits<{ save: [volumes: Volume[]]; cancel: [] }>()
const draft = ref<Volume[]>(JSON.parse(JSON.stringify(props.volumes)) as Volume[])

function normalize(volume: Volume) {
  volume.chapters.forEach((chapter, index) => { chapter.ordinal = index + 1 })
}
function move(volume: Volume, index: number, delta: number) {
  const target = index + delta
  if (target < 0 || target >= volume.chapters.length) return
  const [chapter] = volume.chapters.splice(index, 1)
  volume.chapters.splice(target, 0, chapter)
  normalize(volume)
}
function remove(volume: Volume, index: number) {
  volume.chapters.splice(index, 1)
  normalize(volume)
}
function add(volume: Volume) {
  const ordinal = volume.chapters.length + 1
  const suffix = crypto.randomUUID().slice(0, 8)
  volume.chapters.push({
    id: `chapter-${suffix}`, ordinal, title: `新章节 ${ordinal}`, target_words: 3000,
    point_of_view: '第三人称限知',
    beats: [{ id: `beat-${suffix}`, objective: '推进人物选择与长期变化。', anchor_ids: ['character:protagonist'] }],
  })
}
</script>

<template>
  <section class="structure-editor" aria-label="编辑 Novel StoryMap">
    <header><div><p class="eyebrow">卷章调整草稿</p><h3>编辑章节与顺序</h3></div><button class="text-button" @click="emit('cancel')">取消</button></header>
    <article v-for="volume in draft" :key="volume.id">
      <h4>第 {{ volume.ordinal }} 卷 · <input v-model="volume.title" aria-label="卷标题" /></h4>
      <div v-for="(chapter, index) in volume.chapters" :key="chapter.id" class="structure-edit-row novel-structure-edit-row">
        <span>{{ volume.ordinal }}-{{ chapter.ordinal }}</span>
        <label>章标题<input v-model="chapter.title" /></label>
        <label>目标字数<input v-model.number="chapter.target_words" type="number" min="1" /></label>
        <label>叙述视角<input v-model="chapter.point_of_view" /></label>
        <div><button :disabled="index === 0" @click="move(volume, index, -1)">↑</button><button :disabled="index === volume.chapters.length - 1" @click="move(volume, index, 1)">↓</button><button @click="remove(volume, index)">删除</button></div>
      </div>
      <button class="secondary" @click="add(volume)">＋ 添加章节</button>
    </article>
    <footer><span>保存后形成 Novel 结构候选，不会直接修改正文。</span><button class="primary" :disabled="draft.every((volume) => volume.chapters.length === 0)" @click="emit('save', draft)">保存为结构候选</button></footer>
  </section>
</template>
