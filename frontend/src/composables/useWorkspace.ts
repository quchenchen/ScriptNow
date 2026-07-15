import { ref, computed, watch, onMounted } from 'vue'
import { listEpisodes, updateStage, agentChat, updateProjectSettings } from '../api'
import axios from 'axios'

export function useWorkspace(projectId: number, initialStage: string) {
  const pipelineStages = ref<any[]>([])
  const stage = ref(initialStage || 'ideation')
  const llmModel = ref('dashscope:deepseek-v4-pro')
  const chatMessages = ref<any[]>([])
  const chatInput = ref('')
  const streaming = ref(false)
  const episodes = ref<any[]>([])
  const viewingEp = ref<any>(null)
  const plans = ref<any[]>([])
  const structureConfirmed = ref(false)

  // Filter state
  const projectGenre = ref<string[]>([])
  const projectStyle = ref('')
  const genreOptions = ['悬疑','科幻','情感','霸总','古装','玄幻','都市','恐怖','喜剧']
  const styleOptions = ['快节奏','慢热文艺','爽文','现实主义','烧脑','轻松治愈','黑色幽默']

  // Asset state
  const chars = ref<any[]>([])
  const allForeshadows = ref<any[]>([])
  const sceneList = ref<{name:string,count:number}[]>([])

  onMounted(async () => {
    try { const { data } = await listEpisodes(projectId); episodes.value = data } catch {}
    try {
      const [pr, cr] = await Promise.all([
        axios.get('/api/projects/pipelines'),
        axios.get(`/api/workspace/${projectId}/chat`)
      ])
      if (pr.data?.script) pipelineStages.value = pr.data.script.stages
      if (cr.data?.length) chatMessages.value = cr.data.map((m:any)=>({role:m.role,text:m.content,agent:m.agent_name||undefined}))
    } catch {}
    if (!pipelineStages.value.length) pipelineStages.value = [
      {key:'ideation',label:'灵感孵化'},{key:'structure',label:'故事架构'},{key:'writing',label:'剧本撰写'},
      {key:'review',label:'质量审核'},{key:'polish',label:'润色'},{key:'assets',label:'资产提取'},{key:'prompts',label:'提示词'},
    ]
  })

  const unitLabel = computed(()=>({novel:'章',video_prompt:'场景'}as any)['script'] || '集')
  const isWriting = computed(()=>['writing','outline'].includes(stage.value))

  async function switchStage(s:string) {
    stage.value = s
    try { await updateStage(projectId, s) } catch {}
    if (s==='ideation') { plans.value = []; structureConfirmed.value = false }
    if (s==='writing') await loadEpisodes()
  }

  async function loadEpisodes() {
    try { const { data } = await listEpisodes(projectId); episodes.value = data; loadAssets() } catch {}
  }

  function sendChat() {
    if (!chatInput.value.trim() || streaming.value) return
    const msg = chatInput.value; chatInput.value = ''
    if (stage.value==='ideation' && (projectGenre.value.length||projectStyle.value)) {
      let ctx = '要求：'
      if (projectGenre.value.length) ctx += `类型=${projectGenre.value.join('/')}。`
      if (projectStyle.value) ctx += `风格=${projectStyle.value}。`
      chatMessages.value.push({role:'agent',text:ctx,agent:'系统'})
    }
    chatMessages.value.push({role:'user',text:msg})
    const am:any = {role:'agent',text:'',agent:agentNameForStage(stage.value),time:now()}
    chatMessages.value.push(am); streaming.value = true
    agentChat(projectId, msg, llmModel.value, (d:any)=>{
      if (d.type==='text_delta') { am.text += d.text; am.text = am.text.replace(/\n/g,'<br>') }
      else if (d.type==='done') { streaming.value = false; if (am.text) parsePlans(am.text.replace(/<br>/g,'\n')); loadEpisodes() }
      else if (d.type==='error') { am.text = '❌ '+d.text; streaming.value = false }
    })
  }

  function parsePlans(t:string) {
    const r = /<PLAN\s+id="([ABC])"\s+title="([^"]+)"\s+genre="([^"]+)"\s+hook="([^"]+)"/g; let m; const o:any[]=[]
    while((m=r.exec(t))!==null) o.push({id:m[1],title:m[2],genre:m[3],hook:m[4]})
    if (o.length) { plans.value = o; return }
    const md = /[*]{2}方案([ABC])[：:]\s*(.+?)[*]{2}/g
    while((m=md.exec(t))!==null) o.push({id:m[1],title:m[2].trim(),genre:'',hook:''})
    if (o.length) plans.value = o
  }

  function selectPlan(p:any) {
    chatMessages.value.push({role:'user',text:`选方案${p.id}：${p.title}`})
    switchStage('structure')
    const am:any = {role:'agent',text:'生成中…',agent:'编剧架构师',time:now()}
    chatMessages.value.push(am); streaming.value = true
    agentChat(projectId, `基于方案${p.id}「${p.title}」(${p.hook}，${p.genre})生成完整架构。产出：梗概、角色设定、分集大纲。`, llmModel.value, (d:any)=>{
      if (d.type==='text_delta') { am.text = am.text.replace('生成中…','') + d.text; am.text = am.text.replace(/\n/g,'<br>') }
      else if (d.type==='done') { streaming.value = false }
      else if (d.type==='error') { am.text = '❌ '+d.text; streaming.value = false }
    })
  }

  function generateNext() {
    const ne = episodes.value.length + 1
    const pe = episodes.value[episodes.value.length-1]
    let p = `撰写第${ne}${unitLabel.value}。【场景】△动作 角色：对白。`
    if (pe) { const ps = parseScenes(pe.scenes||''); p += `前情:${ps.slice(-150)}` }
    p += '结尾埋钩子。'
    chatMessages.value.push({role:'user',text:p})
    const am:any = {role:'agent',text:'',agent:'WritingAgent',time:now()}
    chatMessages.value.push(am); streaming.value = true
    agentChat(projectId, p, llmModel.value, (d:any)=>{
      if (d.type==='text_delta') { am.text += d.text; am.text = am.text.replace(/\n/g,'<br>') }
      else if (d.type==='done') { streaming.value = false; loadEpisodes() }
      else if (d.type==='error') { am.text = '❌ '+d.text; streaming.value = false }
    })
  }

  function viewEp(ep:any) { viewingEp.value = ep }
  function parseScenes(s:string) { try { const a = JSON.parse(s); if (Array.isArray(a)) return a.map((x:any)=>x.content||'').join('\n\n') } catch {} return s }

  // Filter functions
  function toggleGenre(g:string) { const i = projectGenre.value.indexOf(g); i>=0 ? projectGenre.value.splice(i,1) : projectGenre.value.push(g) }
  function resetFilters() { projectGenre.value = []; projectStyle.value = '' }
  function resetIdeation() { plans.value = []; resetFilters() }
  watch([projectGenre, projectStyle], ([g,s])=>{ updateProjectSettings(projectId, {genre:g, style_preference:s}) })

  // Asset functions
  async function loadAssets() {
    try {
      const [cr, fr] = await Promise.all([
        axios.get(`/api/memory/${projectId}/characters`),
        axios.get(`/api/memory/${projectId}/foreshadows`)
      ])
      chars.value = cr.data || []; allForeshadows.value = fr.data || []
      const locs:Record<string,number> = {}
      for (const ep of episodes.value) {
        try { const scs = JSON.parse(ep.scenes||'[]'); for (const s of scs) { const m = (s.content||'').match(/【场景\d+】(.+?)(?:·|\s*-|\n)/); if (m) locs[m[1].trim()] = (locs[m[1].trim()]||0)+1 } } catch {}
      }
      sceneList.value = Object.entries(locs).map(([k,v])=>({name:k,count:v}))
    } catch {}
  }
  async function addCharacter(name:string, role:string) { await axios.post(`/api/memory/${projectId}/characters`,{name,role}); await loadAssets() }
  async function saveChar(c:any) { await axios.put(`/api/memory/${projectId}/characters/${c.id}`,{traits:c.traits,personality:c.personality,arc:c.arc}); await loadAssets() }
  async function deleteChar(id:number) { await axios.put(`/api/memory/${projectId}/characters/${id}`,{status:'deceased'}); await loadAssets() }
  async function addForeshadow(title:string, category:string) { await axios.post(`/api/memory/${projectId}/foreshadows`,{title,category,importance:0.5}); await loadAssets() }
  async function resolveFores(id:number) { await axios.put(`/api/memory/${projectId}/foreshadows/${id}`,{status:'resolved'}); await loadAssets() }
  async function deleteFores(id:number) { await axios.put(`/api/memory/${projectId}/foreshadows/${id}`,{status:'abandoned'}); await loadAssets() }

  // Confirm structure
  async function confirmStructure(cards:any[]) {
    if (structureConfirmed.value || !cards.length) return
    const s = cards.map((x:any)=>`## ${x.title}\n${x.content.replace(/<br>/g,'\n')}`).join('\n\n')
    await axios.post(`/api/workspace/${projectId}/chat`,{role:'agent',content:s,agent_name:'架构确认版'})
    structureConfirmed.value = true
  }

  function exportAll() {
    const es = episodes.value.map((e:any)=>{const s=parseScenes(e.scenes||'');return`第${e.episode_number}集 ${e.title||''}\n${s}\n`}).join('\n---\n\n')
    const b = new Blob([`《黑冰·弱女频》\n\n${es}`],{type:'text/plain;charset=utf-8'})
    const a = document.createElement('a');a.href=URL.createObjectURL(b);a.download='export.txt';a.click();URL.revokeObjectURL(a.href)
  }

  return {
    pipelineStages, stage, llmModel, chatMessages, chatInput, streaming, episodes, viewingEp, plans,
    structureConfirmed, projectGenre, projectStyle, genreOptions, styleOptions,
    chars, allForeshadows, sceneList,
    unitLabel, isWriting,
    switchStage, loadEpisodes, sendChat, selectPlan, generateNext, viewEp, parseScenes,
    toggleGenre, resetFilters, resetIdeation,
    loadAssets, addCharacter, saveChar, deleteChar, addForeshadow, resolveFores, deleteFores,
    confirmStructure, exportAll,
  }
}

// Helpers
function now() { return new Date().toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'}) }
export const stageLabelMap:Record<string,string> = {
  ideation:'灵感孵化',structure:'故事架构',writing:'剧本撰写',review:'质量审核',polish:'润色',assets:'资产提取',prompts:'提示词',
  story_design:'故事设计',characters:'角色',outline:'大纲',proofread:'校对'
}
export const stageBadgeMap:Record<string,string> = {
  ideation:'badge-p',structure:'badge-blue',writing:'badge-g',story_design:'badge-p',characters:'badge-blue',outline:'badge-blue'
}
export const agentNameMap:Record<string,string> = {
  ideation:'创意总监',structure:'编剧架构师',writing:'WritingAgent',story_design:'故事策划师',characters:'角色设计师'
}
export function agentNameForStage(s:string) { return agentNameMap[s] || 'Agent' }
