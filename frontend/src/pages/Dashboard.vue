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

      <!-- Quick-start template cards -->
      <div class="templates-section" v-if="!projects.length || showTemplates">
        <div class="tpl-head">
          <span class="tpl-title">⚡ 快速开始</span>
          <span class="tpl-desc">选一个模板，3 步进入创作</span>
          <button v-if="projects.length" class="tpl-toggle" @click="showTemplates=false">收起</button>
        </div>
        <div class="tpl-grid">
          <div v-for="t in templates" :key="t.id" class="tpl-card" @click="startTemplate(t)">
            <span class="tpl-icon">{{ t.icon }}</span>
            <span class="tpl-name">{{ t.name }}</span>
            <span class="tpl-tag">{{ t.genre }}</span>
            <span class="tpl-hook">{{ t.hook }}</span>
          </div>
        </div>
      </div>
      <button v-if="projects.length && !showTemplates" class="tpl-show-btn" @click="showTemplates=true">⚡ 模板快速开始</button>

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
      <div v-else-if="!projects.length && !showTemplates" class="empty-state">
        <div class="es-icon">🎬</div>
        <div class="es-title">开始你的第一个剧本</div>
        <div class="es-desc">选择创作起点，Agent 会陪你从灵感到成品走完全流程</div>
        <button class="btn-p" style="margin-top:16px" @click="showCreate = true">+ 新建项目</button>
      </div>
    </main>

    <div class="overlay" v-if="showCreate" @click.self="onCancel">
      <CreateProjectWizard :prefill="prefillData" @done="onCreated" @cancel="onCancel" />
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
const showTemplates = ref(true)
const prefillData = ref<any>(null)

// Template cards — common short-drama genres as quick-start shortcuts
const templates = [
  { id: 'sweet', icon: '🔥', name: '甜宠逆袭', genre: '甜宠·逆袭', hook: '契约恋爱遇上隐藏大佬', style: '甜爽', seed: '女主为还债签下契约婚姻，不料对方竟是全城首富，从此开启甜蜜逆袭之路' },
  { id: 'revenge', icon: '🗡️', name: '悬疑复仇', genre: '悬疑·复仇', hook: '身份反转 × 高智商博弈', style: '暗黑', seed: '重生回到被害前一天，这一次她要让所有人付出代价' },
  { id: 'rich', icon: '👑', name: '豪门虐恋', genre: '豪门·虐恋', hook: '身份错位引发的爱恨纠缠', style: '虐心', seed: '她以为自己是真千金，直到那个女人带着DNA报告出现在订婚宴上' },
  { id: 'rebirth', icon: '🌙', name: '穿越重生', genre: '穿越·重生', hook: '带着记忆重来一次', style: '爽文', seed: '死于丈夫和闺蜜的算计后重生回到大学时代，这一次她只为自己而活' },
  { id: 'hidden', icon: '🎭', name: '马甲大佬', genre: '马甲·打脸', hook: '你嘲笑的人恰好是你仰望的神', style: '爽文', seed: '所有人都嘲笑她是乡下来的土包子，却不知道她就是那个让全网跪求出山的XX大师' },
  { id: 'custom', icon: '✨', name: '自定义', genre: '你来定', hook: '从零开始，自由创作', style: '', seed: '' },
]

onMounted(async () => {
  try { const { data } = await listProjects(); projects.value = data } catch { /* ignore */ }
})

function startTemplate(t: typeof templates[0]) {
  if (t.id === 'custom') {
    prefillData.value = null
  } else {
    prefillData.value = {
      genre: t.genre.split('·'),
      style: t.style,
      seed_content: t.seed,
      title_hint: t.name,
    }
  }
  showCreate.value = true
}

function onCreated(project: any) {
  showCreate.value = false
  prefillData.value = null
  emit('create', project)
}
function onCancel() { showCreate.value = false; prefillData.value = null }

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
.toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px }
.toolbar h2 { font-size: 20px; font-weight: 590; color: var(--t1) }
.tb-right { display: flex; align-items: center; gap: 8px }

/* ── Template cards ── */
.templates-section { margin-bottom: 24px }
.tpl-head { display: flex; align-items: center; gap: 8px; margin-bottom: 12px }
.tpl-title { font-size: 13px; font-weight: 590; color: var(--t1) }
.tpl-desc { font-size: 11px; color: var(--t4) }
.tpl-toggle { font-size: 10px; color: var(--t4); background: none; border: none; cursor: pointer; margin-left: auto; font-family: inherit }
.tpl-toggle:hover { color: var(--t2) }
.tpl-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 10px }
.tpl-card {
  display: flex; flex-direction: column; gap: 3px;
  padding: 12px; border-radius: 8px; cursor: pointer;
  background: var(--bg-surface); border: 1px solid var(--bs);
  transition: all .15s;
}
.tpl-card:hover { border-color: var(--accent); background: #1f1f23; transform: translateY(-1px) }
.tpl-icon { font-size: 20px; margin-bottom: 4px }
.tpl-name { font-size: 12px; font-weight: 590; color: var(--t1) }
.tpl-tag { font-size: 10px; color: var(--accent); margin-bottom: 2px }
.tpl-hook { font-size: 10px; color: var(--t3); line-height: 1.4 }
.tpl-show-btn { font-size: 11px; color: var(--t4); background: none; border: 1px dashed var(--bs); border-radius: 6px; padding: 6px 12px; cursor: pointer; margin-bottom: 16px; font-family: inherit; transition: .12s }
.tpl-show-btn:hover { color: var(--t2); border-color: var(--bw) }

/* ── Project grid ── */
.project-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px }
.pj-card { background: var(--bg-surface); border: 1px solid var(--bs); border-radius: var(--r-lg); padding: 16px; cursor: pointer; transition: all .15s }
.pj-card:hover { border-color: var(--bw); background: #1f1f23 }
.pj-name { font-size: 14px; font-weight: 590; color: var(--t1); margin-bottom: 2px }
.pj-type { font-size: 11px; color: var(--t4); margin-bottom: 8px }
.pj-meta { display: flex; align-items: center; gap: 6px; margin-bottom: 8px }
.pj-tag { font-size: 10px; color: var(--t3); background: var(--bg-active); padding: 2px 6px; border-radius: 4px }
.pj-bar { height: 3px; background: var(--bg-hover); border-radius: 1px; overflow: hidden; margin-top: 8px }
.pj-fill { height: 100%; background: var(--accent); border-radius: 1px; transition: width .3s }
.btn-del { background: none; border: none; color: var(--t4); cursor: pointer; font-size: 12px; padding: 0 2px; margin-left: auto; opacity: 0 }
.pj-card:hover .btn-del { opacity: 1 }
.btn-del:hover { color: var(--red) }
.empty-state { display:flex;flex-direction:column;align-items:center;justify-content:center;padding:80px 20px;text-align:center }
.es-icon { font-size:48px;margin-bottom:16px;opacity:.3 }
.es-title { font-size:18px;font-weight:590;color:var(--t1);margin-bottom:6px }
.es-desc { font-size:13px;color:var(--t3);max-width:320px;line-height:1.6;margin-bottom:20px }
.overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 50 }
</style>
