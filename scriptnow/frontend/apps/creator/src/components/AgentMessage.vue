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
      <div v-else-if="block.type === 'table'" class="agent-table-wrap">
        <table>
          <thead><tr><th v-for="header in block.headers" :key="header">{{ header }}</th></tr></thead>
          <tbody>
            <tr v-for="(row, rowIndex) in block.rows" :key="rowIndex">
              <td v-for="(cell, cellIndex) in row" :key="cellIndex">{{ cell }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <blockquote v-else-if="block.type === 'quote'">{{ block.text }}</blockquote>
      <pre v-else-if="block.type === 'code'"><code>{{ block.text }}</code></pre>
      <hr v-else />
    </template>
  </div>
</template>

<style scoped>
.agent-table-wrap{max-width:100%;overflow-x:auto;margin:14px 0;border:1px solid var(--line);border-radius:12px}
table{width:100%;min-width:520px;border-collapse:collapse;background:var(--surface);font-size:.92em}
th,td{padding:10px 12px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line);border-right:1px solid var(--line)}
th:last-child,td:last-child{border-right:0}
thead th{background:var(--soft);color:var(--text);font-weight:700}
tbody tr:last-child td{border-bottom:0}
blockquote{margin:14px 0;padding:10px 14px;border-left:3px solid var(--accent);background:var(--soft);color:var(--muted)}
pre{max-width:100%;overflow:auto;margin:14px 0;padding:14px;border:1px solid var(--line);border-radius:12px;background:var(--soft);color:var(--text);white-space:pre-wrap}
</style>
