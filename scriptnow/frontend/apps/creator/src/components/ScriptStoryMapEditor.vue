<script setup lang="ts">
import { ref } from 'vue'

import type { ScriptState } from '../stores/script'

type Episode = ScriptState['story_map']['episodes'][number]
const props = defineProps<{ episodes: Episode[] }>()
const emit = defineEmits<{ save: [episodes: Episode[]]; cancel: [] }>()
const draft = ref<Episode[]>(JSON.parse(JSON.stringify(props.episodes)) as Episode[])

function normalize(episode: Episode) {
  episode.scenes.forEach((scene, index) => { scene.ordinal = index + 1 })
}
function move(episode: Episode, index: number, delta: number) {
  const target = index + delta
  if (target < 0 || target >= episode.scenes.length) return
  const [scene] = episode.scenes.splice(index, 1)
  episode.scenes.splice(target, 0, scene)
  normalize(episode)
}
function remove(episode: Episode, index: number) {
  episode.scenes.splice(index, 1)
  normalize(episode)
}
function add(episode: Episode) {
  const ordinal = episode.scenes.length + 1
  const suffix = crypto.randomUUID().slice(0, 8)
  episode.scenes.push({
    id: `scene-${suffix}`, ordinal, title: `新场景 ${ordinal}`, duration_seconds_target: 120,
    beats: [{ id: `beat-${suffix}`, objective: '明确这一场的目标与转折。', anchor_ids: ['character:protagonist'] }],
  })
}
</script>

<template>
  <section class="structure-editor" aria-label="编辑 Script StoryMap">
    <header><div><p class="eyebrow">结构调整草稿</p><h3>编辑场次与顺序</h3></div><button class="text-button" @click="emit('cancel')">取消</button></header>
    <article v-for="episode in draft" :key="episode.id">
      <h4>第 {{ episode.ordinal }} 集 · <input v-model="episode.title" aria-label="集标题" /></h4>
      <div v-for="(scene, index) in episode.scenes" :key="scene.id" class="structure-edit-row">
        <span>{{ episode.ordinal }}-{{ scene.ordinal }}</span>
        <label>场标题<input v-model="scene.title" /></label>
        <label>目标时长<input v-model.number="scene.duration_seconds_target" type="number" min="1" /></label>
        <div><button :disabled="index === 0" @click="move(episode, index, -1)">↑</button><button :disabled="index === episode.scenes.length - 1" @click="move(episode, index, 1)">↓</button><button @click="remove(episode, index)">删除</button></div>
      </div>
      <button class="secondary" @click="add(episode)">＋ 添加场景</button>
    </article>
    <footer><span>保存后形成新候选，不会直接修改已采纳结构。</span><button class="primary" :disabled="draft.every((episode) => episode.scenes.length === 0)" @click="emit('save', draft)">保存为结构候选</button></footer>
  </section>
</template>
