<template>
  <div class="dashboard">
    <header>
      <h1>ScriptFlow</h1>
      <div class="user-info">
        <span>{{ user.nickname }} · {{ user.membership_tier === 'expert' ? '⭐专家' : '免费' }} · 🪙{{ user.points }}</span>
        <button class="btn-ghost" @click="$emit('logout')">退出</button>
      </div>
    </header>
    <main>
      <div class="toolbar">
        <h2>我的项目</h2>
        <div class="tb-right">
          <button class="btn-p" @click="showCreate = true">+ 新建项目</button>
        </div>
      </div>
      <div class="project-grid" v-if="projects.length > 0">
        <div v-for="p in projects" :key="p.id" class="pj-card" @click="openProject(p)">
          <div class="pj-name">{{ p.title }}</div>
          <div class="pj-type">{{ typeLabel(p.type) }} · {{ p.target_audience || '未设定' }}</div>
          <div class="pj-meta">
            <span :class="stageBadge(p.current_stage)">{{ stageLabel(p.current_stage) }}</span>
            <span v-if="p.source_mode && p.source_mode !== 'original_pitch'" class="pj-tag">{{ sourceModeLabel(p.source_mode) }}</span>
            <button class="btn-del" @click.stop="handleDelete(p.id)" title="删除">🗑</button>
          </div>
          <div class="pj-bar"><div class="pj-fill" :style="{ width: progressPct(p) + '%' }"></div></div>
        </div>
      </div>
      <div v-else class="empty-state">
        <div class="es-icon">🎬</div>
        <div class="es-title">开始你的第一个剧本</div>
        <div class="es-desc">选择创作起点，Agent 会陪你从灵感到成品走完全流程</div>
        <div class="es-steps">
          <div class="es-step"><span class="es-step-num">1</span> 选择来源</div>
          <div class="es-step"><span class="es-step-num">2</span> 填写基本信息</div>
          <div class="es-step"><span class="es-step-num">3</span> 播下种子</div>
        </div>
        <button class="btn-p" style="margin-top:16px" @click="showCreate = true">+ 新建项目</button>
      </div>
    </main>

    <div class="overlay" v-if="showCreate" @click.self="onCancel">
      <CreateProjectWizard @done="onCreated" @cancel="onCancel" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { listProjects, deleteProject as apiDelete } from '../api'
import CreateProjectWizard from '../components/CreateProjectWizard.vue'

defineProps<{ user: any }>()
const emit = defineEmits(['select', 'logout', 'create'])

const projects = ref<any[]>([])
const showCreate = ref(false)

onMounted(async () => {
  try { const { data } = await listProjects(); projects.value = data } catch { /* ignore */ }
})

function onCreated(project: any) {
  showCreate.value = false
  emit('create', project)
}
function onCancel() { showCreate.value = false }

function openProject(p: any) { emit('select', p) }
function typeLabel(t: string) { return ({ novel: '📖 小说', script: '🎬 剧本', video_prompt: '🎥 视频' } as any)[t] || t }
function sourceModeLabel(m: string) {
  return ({
    original_pitch: '灵感',
    original_synopsis: '梗概',
    original_theme: '主题',
    adapted: '📚 改编',
    rewrite: '✂️ 改写',
  } as any)[m] || m
}
const stageLabel = (s: string) => ({ ideation: '灵感', structure: '架构', writing: '撰写', review: '审核', polish: '润色', assets: '资产', prompts: '提示词',
  story_design:'故事设计',characters:'角色',outline:'大纲',proofread:'校对' } as any)[s] || s
const stageBadge = (s: string) => { const early=['ideation','structure','story_design','characters']; if(early.includes(s)) return 'badge badge-p'; if(s==='writing'||s==='outline') return 'badge badge-blue'; return 'badge badge-g' }

function progressPct(p: any) {
  const stageKeys = ['ideation','structure','writing','review','polish','assets','prompts','story_design','characters','outline','proofread']
  const idx = stageKeys.indexOf(p.current_stage); if (idx < 0) return 0
  return Math.min(100, Math.round(((idx + 1) / stageKeys.length) * 100))
}

async function handleDelete(id: number) {
  if (!confirm('确定删除此项目？所有剧集/章节将被永久删除。')) return
  try { await apiDelete(id); projects.value = projects.value.filter((p: any) => p.id !== id) } catch { /* ignore */ }
}
</script>

<style scoped>
.dashboard { min-height: 100vh; display: flex; flex-direction: column }
header { display: flex; align-items: center; justify-content: space-between; padding: 0 24px; height: 48px; background: var(--bg-panel); border-bottom: 1px solid var(--bs); flex-shrink: 0 }
header h1 { font-size: 16px; font-weight: 590; color: var(--t1) }
.user-info { display: flex; align-items: center; gap: 12px; font-size: 12px; color: var(--t2) }
main { flex: 1; max-width: 900px; margin: 0 auto; padding: 32px 24px; width: 100% }
.top-bar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px }
.top-bar h2 { font-size: 18px; font-weight: 590; color: var(--t1) }
.project-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px }
.pj-card { background: var(--bg-surface); border: 1px solid var(--bs); border-radius: var(--r-lg); padding: 16px; cursor: pointer; transition: all .15s }
.pj-card:hover { border-color: var(--bw); background: #1f1f23 }
.pj-name { font-size: 14px; font-weight: 590; color: var(--t1); margin-bottom: 2px }
.pj-type { font-size: 11px; color: var(--t4); margin-bottom: 8px }
.pj-meta { display: flex; align-items: center; gap: 6px; margin-bottom: 8px }
.pj-tag { font-size: 10px; color: var(--t3); background: var(--bg-active); padding: 2px 6px; border-radius: 4px }
.toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px }
.toolbar h2 { font-size: 20px; font-weight: 590; color: var(--t1) }
.tb-right { display: flex; align-items: center; gap: 8px }

.pj-bar { height: 3px; background: var(--bg-hover); border-radius: 1px; overflow: hidden; margin-top: 8px }
.pj-fill { height: 100%; background: var(--accent); border-radius: 1px; transition: width .3s }
.btn-del { background: none; border: none; color: var(--t4); cursor: pointer; font-size: 12px; padding: 0 2px; margin-left: auto; opacity: 0 }
.pj-card:hover .btn-del { opacity: 1 }
.btn-del:hover { color: var(--red) }
.empty-state { display:flex;flex-direction:column;align-items:center;justify-content:center;padding:80px 20px;text-align:center }
.es-icon { font-size:48px;margin-bottom:16px;opacity:.3 }
.es-title { font-size:18px;font-weight:590;color:var(--t1);margin-bottom:6px }
.es-desc { font-size:13px;color:var(--t3);max-width:320px;line-height:1.6;margin-bottom:20px }
.es-steps { display:flex;gap:24px }
.es-step { display:flex;align-items:center;gap:6px;font-size:12px;color:var(--t4) }
.es-step-num { width:22px;height:22px;border-radius:50%;background:var(--bg-active);color:var(--t2);display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:590 }
.overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 50 }
</style>
