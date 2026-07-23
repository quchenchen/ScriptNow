<script setup lang="ts">
type HandoffSummary = {
  characters: number
  relationships: number
  openThreads: number
  previousTitle: string
  warnings: string[]
} | null

defineProps<{
  unitIntent: string
  unitState: 'adopted' | 'candidate' | 'planned'
  agentHeadline: string
  agentDetail: string
  pendingCount: number
  handoff: HandoffSummary
}>()

defineEmits<{
  openDecisions: []
  openDirectives: []
}>()
</script>

<template>
  <section class="rail-body collaboration-flow">
    <article class="flow-card current">
      <small>这一单元要完成</small>
      <b>{{ unitIntent || '先确定本单元的目标、冲突与情绪落点' }}</b>
      <span>{{ unitState === 'adopted' ? '正文已采用，后续单元将以此为依据' : unitState === 'candidate' ? '已有正文候选，尚未成为作品事实' : '尚未开始正文' }}</span>
    </article>
    <article class="flow-card">
      <small>AI 当前工作</small>
      <b>{{ agentHeadline }}</b>
      <span>{{ agentDetail || '你的要求、故事资料和上一单元状态会一起交给写作任务。' }}</span>
    </article>
    <button class="flow-card actionable" @click="$emit('openDecisions')">
      <small>等待你确认</small>
      <b>{{ pendingCount ? `${pendingCount} 项内容不会自动写入作品` : '当前没有待确认内容' }}</b>
      <span>{{ pendingCount ? '查看候选、修改与作品变化' : '你可以继续写作或补充要求' }}</span>
    </button>
    <article class="flow-card handoff">
      <small>确认后带到下一单元</small>
      <b v-if="handoff">{{ handoff.characters }} 个角色状态 · {{ handoff.relationships }} 条关系 · {{ handoff.openThreads }} 条未完剧情</b>
      <b v-else>采用故事方向后开始建立连续性</b>
      <span v-if="handoff?.previousTitle">从《{{ handoff.previousTitle }}》继续，不会把未采用候选当成事实。</span>
      <span v-else>只有你采用的正文与作品变化才会成为后续创作依据。</span>
      <em v-for="warning in handoff?.warnings || []" :key="warning">{{ warning }}</em>
    </article>
    <button class="rail-directive-shortcut" @click="$emit('openDirectives')">补充这一单元必须做到的事</button>
  </section>
</template>
