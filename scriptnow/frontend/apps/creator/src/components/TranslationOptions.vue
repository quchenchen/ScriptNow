<script setup lang="ts">
defineProps<{
  mode: 'none' | 'faithful'
  targetLanguage: string
  sourceLanguage?: string
}>()

const emit = defineEmits<{
  'update:mode': [value: 'none' | 'faithful']
  'update:targetLanguage': [value: string]
}>()

const languages = [
  ['zh-CN', '简体中文'],
  ['zh-TW', '繁體中文'],
  ['en-US', 'English'],
  ['es-ES', 'Español'],
  ['fr-FR', 'Français'],
  ['de-DE', 'Deutsch'],
  ['ja-JP', '日本語'],
  ['ko-KR', '한국어'],
  ['pt-BR', 'Português'],
  ['id-ID', 'Bahasa Indonesia'],
] as const
</script>

<template>
  <section class="translation-options">
    <div class="translation-heading">
      <div>
        <strong>翻译</strong>
        <small>生成独立的翻译导出，不改动已确认正文。</small>
      </div>
      <span v-if="sourceLanguage">原文 · {{ sourceLanguage }}</span>
    </div>
    <div class="translation-mode-grid">
      <button type="button" :class="{ active: mode === 'none' }" @click="emit('update:mode', 'none')">
        <strong>不翻译</strong><small>按作品原语言导出</small>
      </button>
      <button type="button" :class="{ active: mode === 'faithful' }" @click="emit('update:mode', 'faithful')">
        <strong>常规翻译</strong><small>忠实对应原作，保留世界观、情节、语气与结构</small>
      </button>
      <button type="button" class="coming-soon" disabled>
        <strong>归化翻译 <em>敬请期待</em></strong>
        <small>面向目标语言重做世界观、情节、风俗与衣食住行等本土化适配</small>
      </button>
    </div>
    <label v-if="mode === 'faithful'" class="translation-target">
      <span>目标语言</span>
      <select :value="targetLanguage" @change="emit('update:targetLanguage', ($event.target as HTMLSelectElement).value)">
        <option value="" disabled>请选择目标语言</option>
        <option v-for="[value, label] in languages" :key="value" :value="value" :disabled="value === sourceLanguage">
          {{ label }}
        </option>
      </select>
      <small>常规翻译不会替换文化背景或改写剧情。</small>
    </label>
  </section>
</template>
