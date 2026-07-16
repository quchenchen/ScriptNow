<template>
  <div class="shell">
    <nav class="icon-bar">
      <div class="ib-logo">S</div>
      <button class="ib-btn active">📁</button><button class="ib-btn">📜</button><button class="ib-btn">⚙</button>
      <div class="ib-spacer"></div><button class="ib-btn" @click="$emit('logout')">🚪</button>
    </nav>
    <div class="view">
      <header class="top-bar">
        <button class="tb-back" @click="$emit('back')">←</button>
        <span class="tb-title">{{ typeEmoji }}{{ project.title }}</span>
        <span class="tb-meta">v1 · {{ user.membership_tier==='expert'?'专家':'免费' }}</span>
        <div class="view-tabs">
          <button class="vt" :class="{on: view==='workflow'}" @click="view='workflow'">🔀 工作流</button>
          <button class="vt" :class="{on: view==='storyboard'}" @click="view='storyboard'">🎬 故事板</button>
        </div>
        <span class="tb-spacer"></span>
        <ModelSelect v-model="llmModel" />
        <span :class="'tb-badge '+(stageBadgeMap[stage]||'writing')">{{ stageLabelMap[stage]||stage }}</span>
        <button class="tb-btn" :class="{on:chatOpen}" @click="chatOpen=!chatOpen">💬</button>
        <button class="tb-btn" :class="{on:assetOpen}" @click="assetOpen=!assetOpen">📦</button>
      </header>

      <!-- ═══ View: Workflow (vue-flow canvas) ═══ -->
      <Splitpanes v-if="view==='workflow'" class="flow-view" @resized="onPaneResized">
        <Pane :size="chatOpen ? 75 : 100" min-size="40">
          <WorkflowCanvas
            :project="project"
            :sources="sources"
            :plans="plans"
            :structure-cards="structureCards"
            :structure-confirmed="structureConfirmed"
            :episodes="episodes"
            :current-stage="stage"
            :pipeline-stages="pipelineStages"
            @switch-stage="onNodeSwitchStage"
            @open-pitch="onNodeSwitchStage('ideation')"
            @open-source="onNodeSwitchStage('ideation')"
          />
        </Pane>
        <Pane v-if="chatOpen" :size="25" min-size="15" max-size="50">
          <aside class="right-panel fill">
            <div class="rp-head"><span><span class="live-dot"></span>Agent</span><div style="display:flex;gap:2px"><button class="tb-btn sm" @click="chatMessages=[]">🗑</button><button class="tb-btn sm" @click="chatOpen=false">✕</button></div></div>
            <div class="rp-body" style="padding:8px">
              <div v-for="(msg,i) in chatMessages" :key="i" :class="msg.role==='user'?'msg-u':'msg-a'">
                <div v-if="msg.role==='user'" class="bubble-u">{{ msg.text }}</div>
                <div v-else><div class="msg-a-head">{{ msg.agent||'Agent' }}<span class="msg-a-time">{{ msg.time }}</span></div><div class="msg-a-body" v-html="msg.text"></div></div>
              </div>
            </div>
            <div class="rp-foot"><textarea v-model="chatInput" placeholder="输入指令…" @keydown.enter.exact.prevent="sendChat" :disabled="streaming" rows="2"></textarea><button class="btn-p btn-sm" @click="sendChat" :disabled="streaming">{{ streaming?'…':'发' }}</button></div>
          </aside>
        </Pane>
      </Splitpanes>

      <!-- ═══ View: Storyboard (existing stage-driven UI) ═══ -->
      <template v-else>
      <div class="stage-bar">
        <span v-for="s in pipelineStages" :key="s.key" :class="stageClass(s.key)" @click="switchStage(s.key)"><span class="dot"></span>{{ s.label }}</span>
      </div>
      <Splitpanes class="main-row">
        <Pane min-size="15" :size="leftSize">
          <aside class="left-panel fill">
            <div class="lp-section"><SourcePanel :project-id="project.id" :kind="project.source_mode === 'rewrite' ? 'rewrite' : 'adaptation'" /></div>
            <div class="lp-section"><h4>📖 分集 ({{ episodes.filter((e:any)=>e.status==='done').length }}/{{ project.total_episodes||80 }})</h4>
              <div v-for="ep in episodes" :key="ep.episode_number" :class="['lp-ep',{sel:viewingEp?.episode_number===ep.episode_number}]" @click="viewEp(ep)">
                <span class="lp-ep-num">{{ String(ep.episode_number).padStart(2,'0') }}</span><span class="lp-ep-name">{{ ep.title||'待生成' }}</span><span v-if="ep.status==='done'" class="lp-ep-ok">✓</span>
              </div>
            </div>
          </aside>
        </Pane>
        <Pane min-size="30">
          <main class="center">
            <!-- Stage: Ideation -->
            <template v-if="stage==='ideation'">
              <h2>灵感孵化</h2><p class="desc">生成3个差异化创意方案</p>
              <div v-if="!plans.length" class="filter-panel">
                <div class="fp-head"><span class="fp-title">🎯 创作偏好</span><span class="fp-desc">选择后 Agent 将基于偏好生成方案</span><span class="fp-reset" @click="resetFilters" v-if="projectGenre.length||projectStyle">重置</span></div>
                <div class="fp-row"><span class="fp-label">类型</span><div class="fp-chips"><span v-for="g in genreOptions" :key="g" :class="['fp-chip',{on:projectGenre.includes(g)}]" @click="toggleGenre(g)">{{ g }}</span></div></div>
                <div class="fp-row"><span class="fp-label">风格</span><div class="fp-chips"><span v-for="s in styleOptions" :key="s" :class="['fp-chip',{on:projectStyle===s}]" @click="projectStyle=projectStyle===s?'':s">{{ s }}</span></div></div>
                <div class="fp-active" v-if="projectGenre.length||projectStyle"><span class="fp-badge">当前</span><span v-if="projectGenre.length" class="fp-tag">{{ projectGenre.join('·') }}</span><span v-if="projectStyle" class="fp-tag">{{ projectStyle }}</span></div>
              </div>
              <div class="fp-locked" v-else><span>🎯 {{ projectGenre.length?projectGenre.join('·'):'全类型' }} · {{ projectStyle||'全风格' }}</span><span class="fp-reset" @click="resetIdeation">重新生成</span></div>
              <div class="plans-grid" v-if="plans.length">
                <div v-for="p in plans" :key="p.id" class="plan-card" @click="selectPlan(p)"><div class="plan-badge" :class="'plan-'+p.id">{{ p.id }}</div><div class="plan-title">{{ p.title }}</div><div class="plan-hook">{{ p.hook }}</div><div class="plan-genre">{{ p.genre }}</div></div>
              </div>
            </template>
            <!-- Stage: Structure -->
            <template v-else-if="stage==='structure'">
              <h2>故事架构</h2><p class="desc">基于选中方案生成完整架构</p>
              <div class="struct-cards" v-if="structureCards.length">
                <div v-for="card in structureCards" :key="card.title" class="s-card"><div class="sc-head">{{ card.icon }} {{ card.title }}</div><div class="sc-body" v-html="card.content"></div></div>
                <button class="btn-p" @click="confirmStructure(structureCards)" :disabled="structureConfirmed">{{ structureConfirmed?'✅ 架构已确认':'📋 确认架构' }}</button>
              </div>
            </template>
            <!-- Stage: Writing -->
            <template v-else-if="isWriting">
              <h2>剧本撰写</h2><p class="desc">{{ episodes.length }}/{{ project.total_episodes||80 }} 集 · {{ episodes.filter((e:any)=>e.status==='done').length }}完成</p>
              <div class="w-toolbar"><button class="btn-p btn-sm" @click="generateNext">▶ 生成下一集</button><button class="btn-g btn-sm" @click="exportAll" v-if="episodes.filter((e:any)=>e.status==='done').length">⬇ 导出</button></div>
              <table class="ep-table" v-if="episodes.length">
                <thead><tr><th>#</th><th>标题</th><th>状态</th><th>评分</th><th>字数</th></tr></thead>
                <tbody><tr v-for="ep in episodes" :key="ep.episode_number" :class="{sel:viewingEp?.episode_number===ep.episode_number}" @click="viewEp(ep)"><td>{{ String(ep.episode_number).padStart(2,'0') }}</td><td>{{ ep.title||'—' }}</td><td><span :class="ep.status==='done'?'badge badge-g':ep.status==='in_progress'?'badge badge-a':'badge badge-m'">{{ ep.status==='done'?'✓':ep.status==='in_progress'?'⏳':'—' }}</span></td><td>{{ ep.review_score||'—' }}</td><td>{{ ep.word_count||'—' }}</td></tr></tbody>
              </table>
              <div class="detail-pane" v-if="viewingEp"><div class="dp-head"><h3>EP{{viewingEp.episode_number}} · {{viewingEp.title}}</h3><button class="btn-ghost sm" @click="viewingEp=null">✕</button></div><div class="dp-body"><pre>{{ parseScenes(viewingEp.scenes) }}</pre></div></div>
            </template>
            <!-- Stage: Other -->
            <template v-else>
              <h2>{{ stageLabelMap[stage]||stage }}</h2><p class="desc">{{ stageDesc }}</p>
              <div class="card" v-if="stage==='review'"><button class="btn-p btn-sm" @click="sendDirect('请对全部已生成剧集进行质量审核')">🔍 开始审核</button></div>
              <div class="card" v-else-if="stage==='polish'"><button class="btn-p btn-sm" @click="sendDirect('请润色全部剧集')">✨ 一键润色</button></div>
              <div class="card" v-else-if="stage==='assets'"><button class="btn-p btn-sm" @click="sendDirect('提取角色、场景、道具')">📦 提取资产</button></div>
              <div class="card" v-else-if="stage==='prompts'"><button class="btn-p btn-sm" @click="sendDirect('生成 Seedance 提示词')">🎥 生成提示词</button></div>
              <div class="card" v-else><p style="color:var(--t3)">在 Chat 面板发起指令</p></div>
            </template>
            <!-- Action buttons -->
            <div class="stage-acts" v-if="stageActions.length"><button v-for="a in stageActions" :key="a.label" :class="a.cls" @click="a.action">{{ a.label }}</button></div>
          </main>
        </Pane>
        <!-- Asset Panel -->
        <Pane v-if="assetOpen" :size="20" min-size="12" max-size="35">
          <aside class="right-panel fill">
            <div class="rp-head"><span>📦 资产</span><div style="display:flex;gap:2px"><button class="tb-btn sm" :class="{on:assetTab==='chars'}" @click="assetTab='chars'">角色</button><button class="tb-btn sm" :class="{on:assetTab==='fores'}" @click="assetTab='fores'">伏笔</button><button class="tb-btn sm" :class="{on:assetTab==='scenes'}" @click="assetTab='scenes'">场景</button><button class="tb-btn sm" @click="assetOpen=false">✕</button></div></div>
            <div class="rp-body">
              <template v-if="assetTab==='chars'">
                <div class="rp-add"><input v-model="newCharName" placeholder="角色名" class="rp-input" @keyup.enter="handleAddChar"/><select v-model="newCharRole" class="rp-input" style="width:50px"><option value="supporting">配</option><option value="protagonist">主</option><option value="antagonist">反</option></select><button class="btn-p btn-sm" @click="handleAddChar">+</button></div>
                <div v-for="c in sortedChars" :key="c.id" class="rp-item" @click="editingChar=editingChar===c?null:c"><span class="rp-name">{{ c.name }}</span><span :class="'rp-badge '+(c.role||'supporting')">{{ ({protagonist:'主',antagonist:'反',supporting:'配'}as any)[c.role]||'?' }}</span><span class="rp-meta">EP{{ c.first_appearance||'?' }}</span></div>
                <div v-if="editingChar" class="rp-edit"><input v-model="editingChar.traits" placeholder="特质" class="rp-input"/><input v-model="editingChar.personality" placeholder="性格" class="rp-input"/><input v-model="editingChar.arc" placeholder="弧光" class="rp-input"/><div style="display:flex;gap:4px;margin-top:4px"><button class="btn-p btn-sm" @click="saveChar(editingChar);editingChar=null">保存</button><button class="btn-ghost sm" @click="deleteChar(editingChar.id);editingChar=null">删除</button></div></div>
              </template>
              <template v-else-if="assetTab==='fores'">
                <div class="rp-add"><input v-model="newForesTitle" placeholder="伏笔" class="rp-input" @keyup.enter="handleAddFores"/><select v-model="newForesCat" class="rp-input" style="width:50px"><option value="mystery">悬</option><option value="cliffhanger">钩</option><option value="identity">身</option></select><button class="btn-p btn-sm" @click="handleAddFores">+</button></div>
                <div v-for="f in allForeshadows" :key="f.id" class="rp-item"><span class="rp-name">{{ f.title||f.description }}</span><span :class="'rp-badge '+f.status">{{ ({pending:'待',planted:'埋',resolved:'收',abandoned:'废'}as any)[f.status]||'?' }}</span><button v-if="f.status==='planted'" class="btn-ghost sm" @click="resolveFores(f.id)">回收</button></div>
              </template>
              <template v-else><div v-for="s in sceneList" :key="s.name" class="rp-item"><span class="rp-name">🏠 {{ s.name }}</span><span class="rp-meta">×{{ s.count }}</span></div></template>
            </div>
          </aside>
        </Pane>
        <!-- Chat Panel -->
        <Pane v-if="chatOpen" :size="chatPaneSize" min-size="15" max-size="45">
          <aside class="right-panel fill">
            <div class="rp-head"><span><span class="live-dot"></span>Agent</span><div style="display:flex;gap:2px"><button class="tb-btn sm" @click="chatMessages=[]">🗑</button><button class="tb-btn sm" @click="chatOpen=false">✕</button></div></div>
            <div class="rp-body" style="padding:8px">
              <div v-for="(msg,i) in chatMessages" :key="i" :class="msg.role==='user'?'msg-u':'msg-a'">
                <div v-if="msg.role==='user'" class="bubble-u">{{ msg.text }}</div>
                <div v-else><div class="msg-a-head">{{ msg.agent||'Agent' }}<span class="msg-a-time">{{ msg.time }}</span></div><div class="msg-a-body" v-html="msg.text"></div></div>
              </div>
            </div>
            <div class="rp-foot"><textarea v-model="chatInput" placeholder="输入指令…" @keydown.enter.exact.prevent="sendChat" :disabled="streaming" rows="2"></textarea><button class="btn-p btn-sm" @click="sendChat" :disabled="streaming">{{ streaming?'…':'发' }}</button></div>
          </aside>
        </Pane>
      </Splitpanes>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Splitpanes, Pane } from 'splitpanes'
import 'splitpanes/dist/splitpanes.css'
import ModelSelect from '../components/ModelSelect.vue'
import SourcePanel from '../components/SourcePanel.vue'
import WorkflowCanvas from '../components/WorkflowCanvas.vue'
import { useWorkspace, stageLabelMap, stageBadgeMap } from '../composables/useWorkspace'
import { listSources } from '../api'

const props = defineProps<{ user:any; project:any }>()
const emit = defineEmits(['back','logout'])

const typeEmoji = computed(()=>({novel:'📖 ',video_prompt:'🎥 '}as any)[props.project.type]||'🎬 ')
const w = useWorkspace(props.project.id, props.project.current_stage||'ideation')
const { pipelineStages, stage, llmModel, chatMessages, chatInput, streaming, episodes, viewingEp, plans,
  structureConfirmed, projectGenre, projectStyle, genreOptions, styleOptions, chars, allForeshadows, sceneList,
  isWriting,
  switchStage, sendChat, selectPlan, generateNext, viewEp, parseScenes,
  toggleGenre, resetFilters, resetIdeation,
  saveChar, deleteChar, addCharacter, addForeshadow, resolveFores, confirmStructure, exportAll,
} = w

const chatOpen = ref(true), assetOpen = ref(false), assetTab = ref('chars')
const newCharName = ref(''), newCharRole = ref('supporting'), editingChar = ref<any>(null)
const newForesTitle = ref(''), newForesCat = ref('mystery')

// View toggle
const view = ref<'workflow' | 'storyboard'>('storyboard')
const sources = ref<any[]>([])

// Splitpanes sizing
const leftSize = ref(15) // left sidebar %
const chatPaneSize = ref(22) // chat panel %

async function refreshSources() {
  try { const { data } = await listSources(props.project.id); sources.value = data } catch { /* ignore */ }
}
onMounted(refreshSources)

function onNodeSwitchStage(target: string) {
  view.value = 'storyboard'
  switchStage(target)
}

function onPaneResized(_: any) { /* placeholder for persisting sizes later */ }

const stageDesc = computed(()=>{const s=pipelineStages.value.find((x:any)=>x.key===stage.value);return s?.desc||''})
const stageClass = (s:string)=>{const idx=pipelineStages.value.findIndex((x:any)=>x.key===s),cur=pipelineStages.value.findIndex((x:any)=>x.key===stage.value);if(idx<cur)return'ss done';if(idx===cur)return'ss active';return'ss'}
const stageActions = computed(()=>{
  const idx=pipelineStages.value.findIndex((x:any)=>x.key===stage.value),n=pipelineStages.value[idx+1],p=pipelineStages.value[idx-1]
  const a:any[]=[]
  if(['writing'].includes(stage.value)&&episodes.value.filter((e:any)=>e.status==='done').length>0)a.push({label:`→ ${n?.label||'审核'}`,cls:'btn-p',action:()=>switchStage(n?.key)})
  else if(p)a.push({label:`← ${p.label}`,cls:'btn-a',action:()=>switchStage(p.key)})
  if(n&&!['writing'].includes(stage.value))a.push({label:`→ ${n.label}`,cls:'btn-p',action:()=>switchStage(n.key)})
  return a
})
const structureCards = computed(()=>{
  const ms=chatMessages.value.filter((m:any)=>m.role==='agent');if(!ms.length)return[];const c:any[]=[]
  for(const m of ms.slice(-3)){const t=m.text.replace(/<br>/g,'\n');const s=t.match(/#{1,3}\s*(核心梗概|梗概).*?\n+([\s\S]{20,500}?)(?=\n#{1,3}|\n---|$)/);if(s)c.push({icon:'📖',title:'核心梗概',content:s[2].trim().replace(/\n/g,'<br>')});const ch=t.match(/#{1,3}\s*(角色[设定]*|主要角色).*?\n+([\s\S]{20,2000}?)(?=\n#{1,3}|\n---|$)/);if(ch)c.push({icon:'👤',title:'角色设定',content:ch[2].trim().replace(/\n/g,'<br>')});if(c.length)break};return c
})
const sortedChars = computed(()=>{const o:Record<string,number>={protagonist:0,antagonist:1,supporting:2};return [...chars.value].sort((a,b)=>(o[a.role]??9)-(o[b.role]??9)||(a.first_appearance||0)-(b.first_appearance||0))})
function sendDirect(p:string){chatInput.value=p;sendChat()}
function handleAddChar(){if(newCharName.value.trim()){addCharacter(newCharName.value.trim(),newCharRole.value);newCharName.value=''}}
function handleAddFores(){if(newForesTitle.value.trim()){addForeshadow(newForesTitle.value.trim(),newForesCat.value);newForesTitle.value=''}}
</script>
<style scoped>
/* ── Shell ── */
.shell{display:flex;height:100vh;background:var(--bg-root)}
.icon-bar{width:44px;background:var(--bg-panel);border-right:1px solid var(--border-subtle);display:flex;flex-direction:column;align-items:center;padding:8px 0;gap:4px;flex-shrink:0}
.ib-logo{width:28px;height:28px;background:var(--accent-bg);color:#fff;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:700;margin-bottom:12px}
.ib-btn{width:32px;height:32px;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:16px;color:var(--t3);border:none;background:none;cursor:pointer;transition:all .12s}
.ib-btn:hover,.ib-btn.active{background:var(--bg-active);color:var(--t1)}
.ib-spacer{flex:1}
.view{flex:1;display:flex;flex-direction:column;min-width:0}
.top-bar{display:flex;align-items:center;gap:10px;padding:0 12px;height:44px;background:var(--bg-panel);border-bottom:1px solid var(--border-subtle);flex-shrink:0;font-size:13px}
.tb-back{color:var(--t4);padding:2px 4px;font-size:15px;border-radius:4px;border:none;background:none;cursor:pointer;transition:.12s}.tb-back:hover{color:var(--t1);background:var(--bg-hover)}
.tb-title{font-weight:590;color:var(--t1)}.tb-meta{font-size:10px;color:var(--t4)}.tb-spacer{flex:1}
.tb-btn{background:rgba(255,255,255,.02);border:1px solid var(--border);border-radius:6px;padding:3px 8px;color:var(--t3);font-size:12px;cursor:pointer;transition:all .12s}.tb-btn:hover{background:rgba(255,255,255,.04);color:var(--t1)}.tb-btn.on{border-color:var(--accent);color:var(--accent)}.tb-btn.sm{padding:2px 5px;font-size:10px}
.tb-badge{font-size:10px;font-weight:510;padding:2px 8px;border-radius:3px}.tb-badge.badge-p{background:rgba(113,112,255,.12);color:var(--accent)}.tb-badge.badge-blue{background:rgba(59,130,246,.12);color:#3b82f6}.tb-badge.writing,.tb-badge.badge-g{background:rgba(39,166,68,.12);color:var(--green)}
/* ── View tabs ── */
.view-tabs{display:flex;gap:2px;background:var(--bg-active);border-radius:6px;padding:2px;margin-left:8px}
.vt{background:transparent;border:none;color:var(--t3);font-size:11px;padding:3px 10px;border-radius:4px;cursor:pointer;transition:all .12s;font-family:inherit;font-weight:510}
.vt:hover{color:var(--t1)}
.vt.on{background:var(--bg-surface);color:var(--t1);box-shadow:0 1px 2px rgba(0,0,0,.2)}
/* ── Workflow view ── */
.flow-view{flex:1;overflow:hidden}
/* ── Storyboard view ── */
.stage-bar{display:flex;gap:0;padding:4px 12px;background:var(--bg-panel);border-bottom:1px solid var(--border-subtle);flex-shrink:0;overflow-x:auto}.stage-bar::-webkit-scrollbar{display:none}
.ss{display:flex;align-items:center;gap:5px;padding:4px 10px;border-radius:6px;cursor:pointer;white-space:nowrap;color:var(--t4);border:1px solid transparent;transition:all .15s;font-size:12px;user-select:none}.ss:hover{background:var(--bg-hover);color:var(--t3)}.ss.active{color:var(--t1);background:var(--bg-active);border-color:var(--border)}.ss.done{color:var(--t2)}.ss .dot{width:5px;height:5px;border-radius:50%}.ss.done .dot{background:var(--green)}.ss.active .dot{background:var(--accent);box-shadow:0 0 6px var(--accent)}
.main-row{flex:1;overflow:hidden}
/* ── Panels ── */
.fill{width:100%;height:100%}
.left-panel{background:var(--bg-panel);border-right:1px solid var(--border-subtle);overflow-y:auto;padding:12px;height:100%}.lp-section{margin-bottom:16px}.lp-section h4{font-size:9px;font-weight:590;color:var(--t4);text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px}.lp-upload{border:1px dashed var(--border);border-radius:6px;padding:10px;text-align:center;font-size:11px;color:var(--t4);cursor:pointer;transition:.12s}.lp-upload:hover{border-color:var(--accent)}.lp-ep{display:flex;align-items:center;gap:6px;padding:4px 8px;border-radius:4px;cursor:pointer;font-size:11px;color:var(--t3);transition:.1s}.lp-ep:hover{background:var(--bg-hover);color:var(--t2)}.lp-ep.sel{background:var(--bg-active);color:var(--t1)}.lp-ep-num{font-size:10px;color:var(--t4);min-width:20px;font-weight:510}.lp-ep-name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.lp-ep-ok{color:var(--green);font-size:10px}
.center{flex:1;padding:20px 24px;overflow-y:auto;height:100%}.center h2{font-size:18px;font-weight:590;margin-bottom:2px;letter-spacing:-.01em}.desc{font-size:12px;color:var(--t3);margin-bottom:20px}
.right-panel{background:var(--bg-panel);border-left:1px solid var(--border-subtle);display:flex;flex-direction:column;height:100%}.rp-head{display:flex;align-items:center;justify-content:space-between;padding:8px 10px;border-bottom:1px solid var(--border-subtle);font-size:12px;font-weight:590}.rp-body{flex:1;overflow-y:auto;padding:8px}.rp-foot{display:flex;gap:4px;padding:6px;border-top:1px solid var(--border-subtle)}.rp-foot textarea{flex:1;min-height:40px;resize:none;background:rgba(255,255,255,.03);border:1px solid var(--border);border-radius:6px;padding:6px;color:var(--t1);font-size:12px;font-family:inherit;outline:none}.rp-foot textarea:focus{border-color:var(--accent)}
.rp-add{display:flex;gap:4px;margin-bottom:8px}.rp-input{background:rgba(255,255,255,.03);border:1px solid var(--border);border-radius:4px;padding:3px 6px;color:var(--t1);font-size:11px;font-family:inherit;outline:none;flex:1}.rp-input:focus{border-color:var(--accent)}
.rp-item{display:flex;align-items:center;gap:6px;padding:5px 8px;border-radius:4px;cursor:pointer;font-size:11px;color:var(--t2);transition:.1s;border:1px solid transparent}.rp-item:hover{background:var(--bg-hover);border-color:var(--border-subtle)}.rp-name{font-weight:510;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.rp-badge{font-size:9px;padding:1px 5px;border-radius:3px}.rp-badge.protagonist,.rp-badge.主{background:rgba(113,112,255,.15);color:var(--accent)}.rp-badge.antagonist,.rp-badge.反{background:rgba(239,68,68,.15);color:#ef4444}.rp-badge.supporting,.rp-badge.配{background:var(--bg-hover);color:var(--t3)}.rp-badge.planted,.rp-badge.埋{background:rgba(39,166,68,.12);color:var(--green)}.rp-meta{font-size:10px;color:var(--t4);margin-left:auto}
.rp-edit{background:var(--bg-surface);border:1px solid var(--border);border-radius:6px;padding:8px;margin-top:4px;display:flex;flex-direction:column;gap:4px}.live-dot{width:6px;height:6px;border-radius:50%;background:var(--green);display:inline-block;margin-right:4px;animation:pulse 2s infinite}@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.msg-u{display:flex;justify-content:flex-end;margin-bottom:10px}.bubble-u{background:var(--accent-bg);color:#fff;border-radius:10px 10px 4px 10px;padding:6px 10px;font-size:12px;max-width:85%;word-break:break-word}.msg-a{margin-bottom:10px}.msg-a-head{font-size:9px;font-weight:590;color:var(--accent);text-transform:uppercase;letter-spacing:.04em;margin-bottom:2px;display:flex;justify-content:space-between}.msg-a-time{font-size:8px;color:var(--t4);font-weight:400}.msg-a-body{font-size:12px;color:var(--t2);line-height:1.65}
.btn-p{background:var(--accent-bg);color:#fff;padding:5px 12px;border-radius:6px;font-size:12px;font-weight:510;cursor:pointer;border:none;font-family:inherit;transition:all .12s}.btn-p:hover{filter:brightness(1.1)}.btn-p:disabled{opacity:.4;filter:none}.btn-sm{padding:3px 8px;font-size:11px}.btn-a{background:rgba(234,179,8,.1);color:var(--amber);border:1px solid rgba(234,179,8,.2);padding:5px 12px;border-radius:6px;font-size:12px;cursor:pointer;font-family:inherit;transition:.12s}.btn-a:hover{background:rgba(234,179,8,.15)}.btn-g{background:rgba(39,166,68,.1);color:var(--green);border:1px solid rgba(39,166,68,.2);padding:5px 12px;border-radius:6px;font-size:12px;cursor:pointer;font-family:inherit;transition:.12s}.btn-ghost{background:rgba(255,255,255,.02);border:1px solid var(--border);border-radius:6px;padding:4px 10px;color:var(--t3);cursor:pointer;font-size:11px;font-family:inherit;transition:.12s}.btn-ghost:hover{background:var(--bg-hover);color:var(--t1)}.btn-ghost.sm{padding:2px 6px;font-size:10px}
.badge{display:inline-flex;padding:1px 6px;border-radius:3px;font-size:10px;font-weight:510;line-height:16px}.badge-g{background:rgba(39,166,68,.15);color:var(--green)}.badge-a{background:rgba(234,179,8,.15);color:var(--amber)}.badge-m{background:var(--bg-hover);color:var(--t3)}
.ep-table{width:100%;border-collapse:collapse;font-size:12px}.ep-table th{text-align:left;padding:6px 8px;font-size:10px;font-weight:590;color:var(--t4);text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid var(--border-subtle)}.ep-table td{padding:7px 8px;border-bottom:1px solid var(--border-subtle);color:var(--t2)}.ep-table tr:hover td{background:var(--bg-hover);cursor:pointer}.ep-table tr.sel td{background:var(--bg-active)}.detail-pane{border-top:1px solid var(--border);margin-top:12px;background:var(--bg-surface);border-radius:8px}.dp-head{display:flex;align-items:center;justify-content:space-between;padding:10px 14px;border-bottom:1px solid var(--border-subtle)}.dp-head h3{font-size:13px;font-weight:590}.dp-body{padding:14px;font-size:13px;color:var(--t2);line-height:1.9;white-space:pre-wrap}.dp-body pre{font-family:inherit;margin:0}
.plans-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px;margin-bottom:16px}.plan-card{background:var(--bg-surface);border:1px solid var(--border);border-radius:8px;padding:16px;cursor:pointer;transition:all .15s}.plan-card:hover{border-color:var(--accent);box-shadow:0 0 0 1px var(--border)}.plan-badge{width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:590;margin-bottom:10px}.plan-A{background:rgba(113,112,255,.15);color:var(--accent)}.plan-B{background:rgba(39,166,68,.15);color:var(--green)}.plan-C{background:rgba(234,179,8,.15);color:var(--amber)}.plan-title{font-size:14px;font-weight:590;margin-bottom:6px;letter-spacing:-.01em}.plan-hook{font-size:12px;color:var(--t3);line-height:1.55;margin-bottom:6px}.plan-genre{font-size:10px;color:var(--t4)}
.struct-cards{display:flex;flex-direction:column;gap:12px;margin-bottom:16px}.s-card{background:var(--bg-surface);border:1px solid var(--border);border-radius:8px;padding:16px}.sc-head{font-size:14px;font-weight:590;margin-bottom:8px;display:flex;align-items:center;gap:6px}.sc-body{font-size:13px;color:var(--t2);line-height:1.7}.sc-body p{margin-bottom:6px}
.filter-panel{background:var(--bg-surface);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:20px}.fp-head{display:flex;align-items:center;gap:10px;margin-bottom:12px}.fp-title{font-size:14px;font-weight:590}.fp-desc{font-size:11px;color:var(--t4)}.fp-reset{font-size:10px;color:var(--accent);cursor:pointer;margin-left:auto}.fp-reset:hover{text-decoration:underline}.fp-row{display:flex;align-items:flex-start;gap:8px;margin-bottom:8px}.fp-label{font-size:11px;color:var(--t3);min-width:28px;padding-top:5px}.fp-chips{display:flex;flex-wrap:wrap;gap:4px}.fp-chip{padding:4px 10px;border-radius:6px;font-size:11px;cursor:pointer;color:var(--t3);background:rgba(255,255,255,.02);border:1px solid var(--border-subtle);transition:all .12s;user-select:none}.fp-chip:hover{color:var(--t2);background:var(--bg-hover);border-color:var(--border)}.fp-chip.on{color:var(--accent);background:rgba(113,112,255,.1);border-color:var(--accent)}.fp-active{display:flex;align-items:center;gap:6px;margin-top:10px;padding-top:10px;border-top:1px solid var(--border-subtle)}.fp-badge{font-size:10px;color:var(--t4)}.fp-tag{font-size:10px;color:var(--t2);background:var(--bg-hover);padding:2px 8px;border-radius:4px}.fp-locked{display:flex;align-items:center;justify-content:space-between;padding:10px 16px;background:var(--bg-surface);border:1px solid var(--border);border-radius:8px;margin-bottom:20px;font-size:12px;color:var(--t2)}.card{background:var(--bg-surface);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:12px}.w-toolbar{display:flex;gap:6px;margin-bottom:12px}.stage-acts{display:flex;gap:6px;margin-top:16px}
/* ── Splitpanes dark theming ── */
:deep(.splitpanes__splitter){background:var(--bg-panel);border:none;position:relative;z-index:1}
:deep(.splitpanes__splitter::before){content:'';position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:3px;height:24px;background:var(--border-subtle);border-radius:2px;transition:.15s}
:deep(.splitpanes__splitter:hover::before){background:var(--accent);height:32px}
:deep(.splitpanes--horizontal>.splitpanes__splitter){height:4px;cursor:row-resize}
:deep(.splitpanes--vertical>.splitpanes__splitter){width:4px;cursor:col-resize}
</style>
