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
            <span class="pj-ver">v1</span>
            <button class="btn-del" @click.stop="handleDelete(p.id)" title="删除">🗑</button>
          </div>
          <div class="pj-bar"><div class="pj-fill" :style="{ width: progressPct(p) + '%' }"></div></div>
        </div>
      </div>
      <div v-else class="empty-state">
        <div class="es-icon">🎬</div>
        <div class="es-title">开始你的第一个剧本</div>
        <div class="es-desc">选择类型和风格，AI Agent 将帮助你从灵感到成品全流程创作</div>
        <div class="es-steps">
          <div class="es-step"><span class="es-step-num">1</span> 输入创意</div>
          <div class="es-step"><span class="es-step-num">2</span> 选择方案</div>
          <div class="es-step"><span class="es-step-num">3</span> 逐集生成</div>
        </div>
        <button class="btn-p" style="margin-top:16px" @click="showCreate = true">+ 新建项目</button>
      </div>
    </main>

    <!-- Create Dialog -->
    <div class="overlay" v-if="showCreate" @click.self="showCreate = false">
      <div class="dialog">
        <h3>新建项目</h3>
        <div class="form-row"><label>创作类型</label>
          <div class="radio-group">
            <label class="radio" :class="{sel: form.type==='novel'}"><input type="radio" v-model="form.type" value="novel" /> 📖 小说</label>
            <label class="radio" :class="{sel: form.type==='script'}"><input type="radio" v-model="form.type" value="script" /> 🎬 剧本</label>
            <label class="radio" :class="{sel: form.type==='video_prompt'}"><input type="radio" v-model="form.type" value="video_prompt" /> 🎥 视频提示词</label>
          </div>
        </div>
        <div class="form-row"><label>标题</label><input v-model="form.title" placeholder="输入剧本标题" /></div>
        <div class="form-row"><label>目标受众</label>
          <select v-model="form.target_audience"><option value="男频">男频</option><option value="女频">女频</option><option value="通用">通用</option></select>
        </div>
        <div class="form-row"><label>文化背景</label>
          <select v-model="form.cultural_background"><option value="国内">国内</option><option value="海外">海外</option></select>
        </div>
        <div class="form-row"><label>题材类型 <span class="hint">（可多选，Agent 生成方案时依据）</span></label>
          <div class="chips">
            <span v-for="g in genreOptions" :key="g"
              :class="['chip', {on: form.genre.includes(g)}]" @click="toggleGenre(g)">{{ g }}</span>
          </div>
        </div>
        <div class="form-row"><label>叙事风格 <span class="hint">（单选，可留空）</span></label>
          <div class="chips">
            <span v-for="s in styleOptions" :key="s"
              :class="['chip', {on: form.style_preference===s}]"
              @click="form.style_preference = form.style_preference===s ? '' : s">{{ s }}</span>
          </div>
        </div>
        <div class="dialog-actions">
          <button class="btn" @click="showCreate = false">取消</button>
          <button class="btn-p" @click="handleCreate" :disabled="!form.title">创建</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { listProjects, createProject, deleteProject as apiDelete } from '../api'

defineProps<{ user: any }>()
const emit = defineEmits(['select', 'logout', 'create'])

const projects = ref<any[]>([])
const showCreate = ref(false)
const form = ref({ type: 'script', title: '', target_audience: '男频', cultural_background: '国内' })

onMounted(async () => {
  try { const { data } = await listProjects(); projects.value = data } catch {}
})

async function handleCreate() {
  try {
    const { data } = await createProject({ ...form.value, user_id: 1, genre: '[]' })
    emit('create', data); showCreate.value = false
  } catch {}
}

function openProject(p: any) { emit('select', p) }
function typeLabel(t: string) { return ({ novel: '📖 小说', script: '🎬 剧本', video_prompt: '🎥 视频' } as any)[t] || t }
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
  try { await apiDelete(id); projects.value = projects.value.filter((p: any) => p.id !== id) } catch {}
}
</script>

<style scoped>
.dashboard { min-height: 100vh; display: flex; flex-direction: column }
header { display: flex; align-items: center; justify-content: space-between; padding: 0 24px; height: 48px; background: var(--bg-panel); border-bottom: 1px solid var(--bs); flex-shrink: 0 }
header h1 { font-size: 16px; font-weight: 590; color: var(--t1) }
.user-info { display: flex; align-items: center; gap: 12px; font-size: 12px; color: var(--t2) }
.user-info .points { font-family: monospace; color: var(--t3) }
main { flex: 1; max-width: 900px; margin: 0 auto; padding: 32px 24px; width: 100% }
.top-bar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px }
.top-bar h2 { font-size: 18px; font-weight: 590; color: var(--t1) }
.project-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px }
.pj-card { background: var(--bg-surface); border: 1px solid var(--bs); border-radius: var(--r-lg); padding: 16px; cursor: pointer; transition: all .15s }
.pj-card:hover { border-color: var(--bw); background: #1f1f23 }
.pj-name { font-size: 14px; font-weight: 590; color: var(--t1); margin-bottom: 2px }
.pj-type { font-size: 11px; color: var(--t4); margin-bottom: 8px }
.pj-meta { display: flex; align-items: center; gap: 6px; margin-bottom: 8px }
.pj-ver { font-size: 10px; color: var(--t4) }
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
.dialog { background: var(--bg-panel); border: 1px solid var(--bw); border-radius: 12px; padding: 24px; width: 400px }
.dialog h3 { font-size: 16px; font-weight: 590; color: var(--t1); margin-bottom: 16px }
.form-row { margin-bottom: 12px }
.form-row label { display: block; font-size: 11px; color: var(--t4); text-transform: uppercase; letter-spacing: .04em; margin-bottom: 4px }
.form-row input, .form-row select { width: 100%; background: rgba(255,255,255,0.03); border: 1px solid var(--bs); border-radius: var(--r-md); padding: 8px 10px; color: var(--t1); font-size: 13px; outline: none }
.form-row input:focus, .form-row select:focus { border-color: var(--accent) }
.radio-group { display: flex; gap: 16px }
.radio { display: flex; align-items: center; gap: 4px; font-size: 13px; color: var(--t2); cursor: pointer }
.dialog-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px }
</style>
