<!--
  ChatMessage.vue — renders a single chat message with structured block
  detection. Parses SF:CHOICE / SF:STATUS / SF:CONFIRM blocks from the
  accumulated agent text and renders them as interactive components.
-->
<template>
  <div :class="msg.role === 'user' ? 'msg-u' : 'msg-a'">
    <!-- User bubble -->
    <div v-if="msg.role === 'user'" class="bubble-u">{{ msg.text }}</div>

    <!-- Agent message with rich blocks -->
    <div v-else>
      <div class="msg-a-head">{{ msg.agent || 'Agent' }}<span class="msg-a-time">{{ msg.time }}</span></div>
      <div class="msg-a-body">
        <template v-for="(block, idx) in parsedBlocks" :key="idx">
          <!-- Status block -->
          <div v-if="block.type === 'status'" class="sf-status">
            <span class="sf-status-badge">{{ block.data.stage }}</span>
            <span class="sf-status-step">{{ block.data.step }}</span>
            <span v-if="block.data.detail" class="sf-status-detail">{{ block.data.detail }}</span>
          </div>

          <!-- Choice block -->
          <div v-else-if="block.type === 'choice'" class="sf-choice">
            <div class="sf-choice-q">{{ block.data.question }}</div>
            <div class="sf-choice-grid">
              <button
                v-for="opt in block.data.options"
                :key="opt.id"
                class="sf-choice-card"
                :class="{ selected: selectedChoice === opt.id, isDefault: opt.id === block.data.default }"
                @click="$emit('quick-reply', opt.id)"
              >
                <span class="sf-choice-id">{{ opt.id }}</span>
                <span class="sf-choice-title">{{ opt.title }}</span>
                <span class="sf-choice-desc">{{ opt.desc }}</span>
              </button>
            </div>
          </div>

          <!-- Confirm block -->
          <div v-else-if="block.type === 'confirm'" class="sf-confirm">
            <div class="sf-confirm-summary">{{ block.data.summary }}</div>
            <ul class="sf-confirm-items">
              <li v-for="(item, i) in block.data.items" :key="i">✓ {{ item }}</li>
            </ul>
            <button class="sf-confirm-btn" @click="$emit('quick-reply', '确认')">📋 确认</button>
          </div>

          <!-- Plain text block -->
          <div v-else class="msg-a-text" v-html="block.html"></div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface SFBlock {
  type: 'text' | 'choice' | 'status' | 'confirm'
  data?: any
  html?: string
}

const props = defineProps<{
  msg: { role: string; text: string; agent?: string; time?: string }
  selectedChoice?: string
}>()

defineEmits<{ (e: 'quick-reply', value: string): void }>()

/**
 * Parse the agent message text into a sequence of blocks.
 * Structured blocks are delimited by <!--SF:TYPE-->...<!--/SF:TYPE--> markers.
 */
const parsedBlocks = computed<SFBlock[]>(() => {
  if (props.msg.role === 'user') return []

  const text = props.msg.text || ''
  const blocks: SFBlock[] = []
  const regex = /<!--SF:(CHOICE|STATUS|CONFIRM)-->\s*([\s\S]*?)\s*<!--\/SF:\1-->/g

  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = regex.exec(text)) !== null) {
    // Text before the block
    if (match.index > lastIndex) {
      const before = text.slice(lastIndex, match.index).trim()
      if (before) blocks.push({ type: 'text', html: before })
    }

    // The structured block
    const blockType = match[1].toLowerCase() as 'choice' | 'status' | 'confirm'
    try {
      const data = JSON.parse(match[2])
      blocks.push({ type: blockType, data })
    } catch {
      // Malformed JSON — render as text
      blocks.push({ type: 'text', html: match[0] })
    }

    lastIndex = match.index + match[0].length
  }

  // Trailing text
  if (lastIndex < text.length) {
    const trailing = text.slice(lastIndex).trim()
    if (trailing) blocks.push({ type: 'text', html: trailing })
  }

  // If no blocks parsed (no structured markers), just return raw text
  if (blocks.length === 0 && text) {
    blocks.push({ type: 'text', html: text })
  }

  return blocks
})
</script>

<style scoped>
/* ── Status block ── */
.sf-status { display: flex; align-items: center; gap: 6px; padding: 4px 0; margin-bottom: 6px }
.sf-status-badge { font-size: 10px; font-weight: 590; padding: 2px 8px; border-radius: 4px; background: rgba(113,112,255,.12); color: var(--accent) }
.sf-status-step { font-size: 11px; color: var(--t2) }
.sf-status-detail { font-size: 10px; color: var(--t4) }

/* ── Choice block ── */
.sf-choice { margin: 10px 0 }
.sf-choice-q { font-size: 12px; font-weight: 590; color: var(--t1); margin-bottom: 8px }
.sf-choice-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 6px }
.sf-choice-card {
  display: flex; flex-direction: column; gap: 2px;
  padding: 8px 10px; border-radius: 6px; cursor: pointer;
  background: rgba(255,255,255,.02); border: 1px solid var(--border);
  transition: all .12s; text-align: left; font-family: inherit;
  color: var(--t2);
}
.sf-choice-card:hover { border-color: var(--accent); background: rgba(113,112,255,.05) }
.sf-choice-card.selected { border-color: var(--accent); background: rgba(113,112,255,.1) }
.sf-choice-card.isDefault { border-color: var(--border); box-shadow: inset 0 0 0 1px rgba(113,112,255,.08) }
.sf-choice-id { font-size: 10px; font-weight: 700; color: var(--accent); margin-bottom: 2px }
.sf-choice-title { font-size: 11px; font-weight: 590; color: var(--t1) }
.sf-choice-desc { font-size: 10px; color: var(--t3); line-height: 1.4 }

/* ── Confirm block ── */
.sf-confirm { margin: 10px 0; padding: 10px; background: var(--bg-surface); border: 1px solid var(--border); border-radius: 8px }
.sf-confirm-summary { font-size: 12px; font-weight: 590; color: var(--t1); margin-bottom: 6px }
.sf-confirm-items { list-style: none; padding: 0; margin: 0 0 8px 0 }
.sf-confirm-items li { font-size: 11px; color: var(--t2); padding: 2px 0 }
.sf-confirm-btn {
  font-size: 11px; padding: 4px 12px; border-radius: 4px; cursor: pointer;
  background: rgba(39,166,68,.1); border: 1px solid rgba(39,166,68,.2);
  color: var(--green); font-family: inherit; transition: .12s;
}
.sf-confirm-btn:hover { background: rgba(39,166,68,.15) }

/* ── Text blocks (inherit parent msg-a-body styles) ── */
.msg-a-text { font-size: 12px; color: var(--t2); line-height: 1.65 }
</style>
