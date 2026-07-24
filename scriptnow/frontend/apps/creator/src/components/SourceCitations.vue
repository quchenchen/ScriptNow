<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

import { api } from '../api'

type RagHit = {
  chunk_id: string
  source_file_id: string
  source_name: string
  ordinal: number
  excerpt: string
  score: number
}

const props = defineProps<{ projectId: string; query?: string }>()
const search = ref(props.query ?? '')
const hits = ref<RagHit[]>([])
const loading = ref(false)
const error = ref('')
const activeId = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    hits.value = await api<RagHit[]>(
      `/projects/${props.projectId}/rag/search?q=${encodeURIComponent(search.value.trim())}`,
    )
  } catch {
    error.value = '原著素材暂时无法检索。'
  } finally {
    loading.value = false
  }
}

watch(() => props.projectId, () => void load())
onMounted(() => void load())
</script>

<template>
  <section class="source-citations" aria-labelledby="source-citations-title">
    <p id="source-citations-title" class="eyebrow">原著引用</p>
    <form class="source-search" role="search" @submit.prevent="load">
      <label class="sr-only" for="source-query">检索原著素材</label>
      <input id="source-query" v-model="search" placeholder="检索人物、事件或原文" />
      <button type="submit" :disabled="loading">{{ loading ? '检索中…' : '检索' }}</button>
    </form>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-else-if="!loading && hits.length === 0" class="source-empty">尚无匹配片段，可更换关键词。</p>
    <ol v-else class="source-results">
      <li v-for="hit in hits" :key="hit.chunk_id">
        <button
          type="button"
          class="source-hit"
          :class="{ active: activeId === hit.chunk_id }"
          :aria-expanded="activeId === hit.chunk_id"
          @click="activeId = activeId === hit.chunk_id ? '' : hit.chunk_id"
        >
          <span><strong>{{ hit.source_name }}</strong> · 片段 {{ hit.ordinal + 1 }}</span>
          <small>{{ activeId === hit.chunk_id ? '收起原文' : '定位原文' }}</small>
        </button>
        <blockquote v-if="activeId === hit.chunk_id">{{ hit.excerpt }}</blockquote>
      </li>
    </ol>
  </section>
</template>
