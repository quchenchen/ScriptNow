<script setup lang="ts">
import { computed } from 'vue'

import { parseAgentMessage } from './agentMessage'

const props = defineProps<{ text: string }>()

const blocks = computed(() => parseAgentMessage(props.text))
</script>

<template>
  <div class="agent-message">
    <template v-for="(block, index) in blocks" :key="index">
      <h3 v-if="block.type === 'heading'" :class="`level-${block.level}`">{{ block.text }}</h3>
      <p v-else-if="block.type === 'paragraph'">{{ block.text }}</p>
      <ol v-else-if="block.type === 'list' && block.ordered"><li v-for="item in block.items" :key="item">{{ item }}</li></ol>
      <ul v-else-if="block.type === 'list'"><li v-for="item in block.items" :key="item">{{ item }}</li></ul>
      <hr v-else />
    </template>
  </div>
</template>
