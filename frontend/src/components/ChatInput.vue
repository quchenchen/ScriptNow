<!--
  ChatInput.vue — rich input bar for the chat panel. Features:
  - Textarea with auto-resize
  - Inline tool buttons: 📎 attach, @角色, 📍 引场景
  - Enter to send, Shift+Enter for newline
  - Emits: send(text), attach(), mention-char(), cite-scene()
-->
<template>
  <div class="ci-wrap">
    <div class="ci-tools">
      <button class="ci-btn" title="附件" @click="$emit('attach')">📎</button>
      <button class="ci-btn" title="@角色" @click="$emit('mention-char')">@</button>
      <button class="ci-btn" title="引用场景" @click="$emit('cite-scene')">📍</button>
    </div>
    <div class="ci-input-row">
      <textarea
        ref="taRef"
        v-model="text"
        :placeholder="placeholder"
        :disabled="disabled"
        rows="1"
        @input="autoResize"
        @keydown.enter.exact.prevent="handleSend"
      ></textarea>
      <button class="ci-send" :disabled="disabled || !text.trim()" @click="handleSend">
        {{ disabled ? '…' : '↑' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'

const props = defineProps<{
  modelValue: string
  disabled?: boolean
  placeholder?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: string): void
  (e: 'send'): void
  (e: 'attach'): void
  (e: 'mention-char'): void
  (e: 'cite-scene'): void
}>()

const taRef = ref<HTMLTextAreaElement | null>(null)

const text = ref(props.modelValue)
watch(() => props.modelValue, v => { text.value = v })
watch(text, v => emit('update:modelValue', v))

function autoResize() {
  nextTick(() => {
    const ta = taRef.value
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 120) + 'px'
  })
}

function handleSend() {
  if (!text.value.trim() || props.disabled) return
  emit('send')
}
</script>

<style scoped>
.ci-wrap {
  border-top: 1px solid var(--border-subtle);
  padding: 4px 6px 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.ci-tools {
  display: flex;
  gap: 2px;
  padding: 0 2px;
}
.ci-btn {
  background: none;
  border: none;
  color: var(--t4);
  font-size: 12px;
  padding: 2px 5px;
  border-radius: 3px;
  cursor: pointer;
  transition: all .1s;
  font-family: inherit;
}
.ci-btn:hover { color: var(--t1); background: var(--bg-hover) }
.ci-input-row {
  display: flex;
  gap: 4px;
  align-items: flex-end;
}
.ci-input-row textarea {
  flex: 1;
  min-height: 32px;
  max-height: 120px;
  resize: none;
  background: rgba(255,255,255,.03);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 10px;
  color: var(--t1);
  font-size: 12px;
  font-family: inherit;
  outline: none;
  line-height: 1.5;
  transition: border-color .12s;
}
.ci-input-row textarea:focus { border-color: var(--accent) }
.ci-input-row textarea:disabled { opacity: .5 }
.ci-send {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: none;
  background: var(--accent-bg);
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all .12s;
  flex-shrink: 0;
}
.ci-send:hover { filter: brightness(1.15) }
.ci-send:disabled { opacity: .3; cursor: default; filter: none }
</style>
