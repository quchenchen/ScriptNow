<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import DashboardPage from './pages/DashboardPage.vue'
import { consumeNdjson } from './ndjson'
import { revisionPayload, selectionFromRange, type TextSelection } from './revision'

// ── Types ──
type MediumKey='vertical-short-drama'|'horizontal-web-series'|'feature-film'|'animated-series'|'novel'|'short-story'|'interactive-narrative'
type StructureKey='three-act'|'five-act'|'kishotenketsu'|'hero-journey'|'save-the-cat'|'eight-sequence'|'syd-field'
type Goal='original-novel'|'original-script'|'adapt-novel'|'adapt-script'
type Screen='dashboard'|'create'|'workspace'
type WorkspaceMode='focus'|'plan'|'review'|'blueprint'
type WorkspaceSpace='work'|'story'|'review'
type RailTab='collaboration'|'continuity'|'directives'|'decisions'
type Architecture={status:string;thesis:string;approach:string;agent_session:Array<Record<string,unknown>>;arcs:Array<{id:number;ordinal:number;title:string;episode_start:number;episode_end:number;core_conflict:string;emotional_landing:string;protag_state:string;antag_state:string;must_have_events:string[];foreshadow_actions:string[];status:string}>}
type StoryCore={id:number;title:string;logline:string;dramatic_question:string;protagonist:string;conflict:string;promise:string;source_strategy:string;status:string}
type AgentTask={id:number;status:string;goal:string;agent_profile:string;status_message:string;candidates:StoryCore[]}
type Pulse={phase:string;state:'working'|'waiting_user'|'ready'|'blocked'|'complete';headline:string;detail:string;needs_user:boolean;next_action:string;capability_tier:string;estimated_credits:number}
type Project={id:number;title:string;goal_type:Goal;genre:string;audience:string;seed:string;status:string;adopted_story_core_id:number|null;source_name:string;source_status:string;task:AgentTask|null;pulse:Pulse|null}
type ProjectPlan={project_id:number;creation_source:string;delivery_medium:'novel'|'script';seed_maturity:string;planning_mode:string;target_volume_count:number;target_chapter_count:number;target_episode_count:number;target_scenes_per_episode:number;target_words:number;target_minutes_per_episode:number;style_direction:string;creative_boundaries:string[];status:string}
type StoryMapUnit={id:number;unit_type:'chapter'|'scene';ordinal:number;global_ordinal:number;title:string;intent:string;status:string;target_length:number;risk_count:number;manuscript_unit_id:number|null}
type StoryMapGroup={id:number;group_type:'volume'|'episode';ordinal:number;title:string;goal:string;status:string;units:StoryMapUnit[]}
type StoryMap={project_id:number;delivery_medium:'novel'|'script';groups:StoryMapGroup[];planned_units:number;adopted_units:number}
type PlanImpact={current_units:number;target_units:number;protected_units:number;units_added:number;units_removed:number;topology_changed:boolean;can_apply:boolean;requires_confirmation:boolean;warnings:string[]}
type Continuity={project_id:number;health:'stable'|'attention'|'risk';entities:Array<{id:number;entity_type:string;name:string;truth:Record<string,unknown>;current_state:Record<string,unknown>;frozen:boolean;source_label:string}>;threads:Array<{id:number;thread_type:string;title:string;setup:string;payoff_target:string;status:string;urgency:string;source_label:string}>;alerts:Array<{id:number;severity:string;message:string}>}
type ContextPreview={ordinal:number;target_label:string;previous_anchor:null|{ordinal:number;title:string;content_tail:string};characters:Array<{name:string;truth:Record<string,unknown>;state:Record<string,unknown>;frozen:boolean}>;relationships:Array<{from:string;to:string;type:string;status:string;description:string}>;open_threads:Array<{id:number;type:string;title:string;status:string;payoff_target:string}>;foreshadows:Array<{id:number;title:string;kind:string;status:string;planned_resolve_ordinal:number|null;urgency:'normal'|'attention'|'urgent'|'overdue'}>;directives:Directive[];memory_updates:Array<{id:number;type:string;title:string;source_unit_id:number;activation:string}>;pending_memory_decisions:Array<{id:number;type:string;title:string;source_unit_id:number;activation:string}>;required_story_facts:Array<{change_id:number;type:string;label:string;requirement:string;action:string}>;warnings:string[]}
type ManuscriptUnit={id:number;scene_id:number|null;unit_type:'chapter'|'scene';ordinal:number;title:string;adopted_content:string;status:string;candidate:null|{id:number;title:string;content:string;status:string;context_pack:Record<string,unknown>;state_delta:Record<string,Record<string,unknown>>;thread_actions:Array<{thread_type:string;action:string;note:string}>;continuity_report:Array<{check:string;status:string;message:string;label?:string;start?:number;end?:number;excerpt?:string}>}}
type ManuscriptMetadata=Record<string,string|string[]>
type ManuscriptDocument={unit_id:number;project_id:number;version:number;content:string;source:string;metadata:ManuscriptMetadata}
type ManuscriptDocumentVersion={version:number;content:string;source:string;metadata:ManuscriptMetadata}
type SaveStatus='idle'|'dirty'|'saving'|'saved'|'failed'|'conflict'
type CreativeRevision={id:number;project_id:number;scene_id:number;status:'candidate'|'adopted'|'rejected'|'stale';candidate_content:string;brief:{goal:string;scope:string[];preserve:string[];constraints:string[]};context_pack:{anchors:Record<string,unknown>};evidence:Array<Record<string,unknown>>;impact:Array<Record<string,unknown>>;stale_reason:string}
type AiEditMode='shorten'|'expand'|'polish'|'dialogue'|'pace'|'custom'
type ManuscriptAiEdit={id:number;project_id:number;unit_id:number;base_version:number;selection_start:number;selection_end:number;selected_text:string;replacement_text:string;mode:AiEditMode;instruction:string;preserve:string[];context_before:string;context_after:string;rationale:string;status:'candidate'|'adopted'|'rejected'|'stale';stale_reason:string}
type LivingAssetCandidate={id:number;project_id:number;revision_id:number;asset_type:'character_state'|'relationship_change'|'timeline_event'|'foreshadow_event'|'world_fact';title:string;proposed_value:{revision_goal:string;before:string;after:string};evidence:Array<Record<string,unknown>>;autonomy_level:string;status:'candidate'|'adopted'|'rejected'}
type ManuscriptImpactCandidate={id:number;project_id:number;edit_revision_id:number;unit_id:number;impact_type:'character_state'|'relationship_change'|'foreshadow_event'|'world_fact';title:string;proposed_value:{instruction:string;before:string;after:string};evidence:Array<Record<string,unknown>>;status:'candidate'|'adopted'|'rejected'}
type StoryBibleChange={id:number;project_id:number;change_type:string;title:string;proposed:Record<string,unknown>;effective_from_ordinal:number;status:'candidate'|'adopted'|'rejected';impacts:Array<{story_map_unit_id:number;ordinal:number;artifact_state:string;proposed_action:string;status:string}>;unaffected_adopted_before:number}
type CascadeRevision={id:number;project_id:number;change_id:number;unit_id:number;base_version:number;original_content:string;candidate_content:string;rationale:string;evidence:Array<{required_fact:Record<string,unknown>;locator:string|null;status:string}>;status:'candidate'|'adopted'|'rejected'|'stale'}
type RuntimeStatus={mode:'platform'|'demo';available:boolean;capability_tier:string}
type Directive={id:number;scope:'next_task'|'project_rule';target_type:'project'|'manuscript_unit'|'agent_task';target_id:number|null;lifetime:'once'|'unit'|'project';instruction:string;preserve:string[];constraints:string[];status:string;consumed_by_task_id:number|null}

const API='http://127.0.0.1:8103'
const route=useRoute(),router=useRouter()
const screen=ref<Screen>('dashboard'),step=ref(1),goal=ref<Goal>('original-script'),mediumKey=ref<MediumKey>('vertical-short-drama')
const railTab=ref<RailTab>('collaboration')
const title=ref(''),seed=ref(''),genre=ref('悬疑'),audience=ref('大众'),sourceName=ref('')
const seedMaturity=ref<'theme'|'pitch'|'synopsis'|'outline'|'draft'>('pitch')
const planningMode=ref<'plan_first'|'progressive'|'import_outline'>('plan_first')
const targetVolumeCount=ref(1),targetChapterCount=ref(12),targetEpisodeCount=ref(3),targetScenesPerEpisode=ref(8),targetWords=ref(0),targetMinutes=ref(12),styleDirection=ref('')
const sourceMethod=ref<'paste'|'upload'|'later'>('paste'),sourceFile=ref<File|null>(null)
const mode=ref<WorkspaceMode>('focus')
// ── Linear phase gating ──
type Phase='review'|'blueprint'|'focus'
const currentPhase=computed<Phase>(()=>{
  if(!current.value) return 'focus'
  const hasCore=!!current.value.adopted_story_core_id
  const hasArch=!!architecture.value?.status&&architecture.value.status!=='not_planned'
  const hasPendingDecisions=current.value.task?.candidates?.some((c:StoryCore)=>c.status==='candidate')
  if(!hasCore&&hasPendingDecisions) return 'review'
  if(hasCore&&!hasArch) return 'blueprint'
  return 'focus'
})
const allowedModes=computed<WorkspaceMode[]>(()=>{
  const p=currentPhase.value
  if(p==='review') return ['review','plan']
  if(p==='blueprint') return ['blueprint','review','plan']
  return ['focus','blueprint','plan','review']
})
const tabDefs=computed(()=>{
  const all:{k:WorkspaceMode,n:string}[]=[{k:'focus',n:'作品'},{k:'blueprint',n:'蓝图'},{k:'plan',n:'故事'},{k:'review',n:'审稿'}]
  return all.filter(t=>allowedModes.value.includes(t.k))
})
// Auto-switch to correct phase on project open
function enterCorrectMode(){
  if(!current.value) return
  const p=currentPhase.value
  if(p==='review'){mode.value='review';return}
  if(p==='blueprint'&&mode.value==='focus'){mode.value='blueprint';return}
}
const projects=ref<Project[]>([]),current=ref<Project|null>(null),continuity=ref<Continuity|null>(null),manuscript=ref<ManuscriptUnit|null>(null),busy=ref(false),error=ref('')
const manuscriptDocument=ref<ManuscriptDocument|null>(null),manuscriptDraft=ref(''),manuscriptSaveStatus=ref<SaveStatus>('idle')
const manuscriptMetadata=ref<ManuscriptMetadata>({})
const manuscriptVersions=ref<ManuscriptDocumentVersion[]>([])
let manuscriptSaveTimer:ReturnType<typeof setTimeout>|undefined
const projectsLoaded=ref(false)
const contextPreview=ref<ContextPreview|null>(null)
const projectPlan=ref<ProjectPlan|null>(null),storyMap=ref<StoryMap|null>(null),currentStoryUnit=ref<StoryMapUnit|null>(null)
const editingStoryUnitId=ref<number|null>(null),storyUnitTitle=ref(''),storyUnitIntent=ref('')
const planVolumeCount=ref(1),planChapterCount=ref(1),planEpisodeCount=ref(1),planScenesPerEpisode=ref(1),planImpact=ref<PlanImpact|null>(null)
const mediums=ref<Array<{key:string;label:string;label_en:string}>>([])
const structures=ref<Array<{key:string;label:string;label_en:string;description:string;best_for:string}>>([])
const storyStructure=ref<StructureKey>('three-act')
const runtime=ref<RuntimeStatus|null>(null)
const architecture=ref<Architecture|null>(null)
const directiveText=ref(''),directives=ref<Directive[]>([]),directiveNotice=ref('')
const selectedText=ref<TextSelection|null>(null),revisionInstruction=ref(''),replacementText=ref(''),revision=ref<CreativeRevision|null>(null)
const aiEditMode=ref<AiEditMode>('polish'),aiEditInstruction=ref(''),manuscriptAiEdit=ref<ManuscriptAiEdit|null>(null)
const aiEditStreamingText=ref('')
const feedbackText=ref('')
const feedbackBusy=ref(false)
const chatHistory=ref<Array<{role:string;text:string;content?:string;candidateId?:number}>>([])
let aiEditAbortController:AbortController|undefined
const assetCandidates=ref<LivingAssetCandidate[]>([])
const manuscriptImpactCandidates=ref<ManuscriptImpactCandidate[]>([])
const storyBibleChanges=ref<StoryBibleChange[]>([])
const cascadeRevisions=ref<CascadeRevision[]>([])
const newEntityType=ref<'character'|'organization'>('character'),newEntityName=ref(''),newEntityIdentity=ref('')
const newCharacterFunction=ref(''),newCharacterVoice=ref(''),newCharacterFirstOrdinal=ref(1),newCharacterRelationTarget=ref<number|null>(null),newCharacterRelationType=ref('')
const relationFrom=ref<number|null>(null),relationTo=ref<number|null>(null),relationType=ref('')
const relationObjective=ref(''),relationFromPerception=ref(''),relationToPerception=ref(''),relationHidden=ref(''),relationEffectiveOrdinal=ref(1)
const foreshadowTitle=ref(''),foreshadowContent=ref(''),foreshadowResolveOrdinal=ref<number|null>(null)
const foreshadowPlantOrdinal=ref(1),foreshadowPlantingMethod=ref(''),foreshadowReinforceOrdinals=ref(''),foreshadowResolutionIntent=ref('')
const worldRuleTitle=ref(''),worldRule=ref(''),worldConstraint=ref(''),worldExceptions=ref(''),worldEffectiveOrdinal=ref(1)
const selectedForeshadowId=ref<number|null>(null),foreshadowAction=ref<'queue'|'plant'|'reinforce'|'partial_resolve'|'resolve'|'abandon'>('plant'),foreshadowEvidence=ref('')
const goals=[{key:'original-novel' as Goal,title:'创作一部小说',desc:'从主题、灵感或大纲开始生长'},{key:'original-script' as Goal,title:'创作一个剧本',desc:'从故事种子长成 Episode 与 Scene'},{key:'adapt-novel' as Goal,title:'把剧本或故事改编成小说',desc:'从已有故事出发，重构视角与文风'},{key:'adapt-script' as Goal,title:'把小说或故事改编成剧本',desc:'从已有文本出发，映射为可拍摄 Scene'}]
const isAdapt=computed(()=>goal.value.startsWith('adapt'))
const isNovel=computed(()=>goal.value.endsWith('novel'))
const goalLabel=computed(()=>goals.find(x=>x.key===goal.value)?.title||'')
const derivedMedium=computed<MediumKey>(()=>goal.value.endsWith('novel')?'novel':goal.value.endsWith('script')&&!goal.value.startsWith('adapt')?'vertical-short-drama':'horizontal-web-series')
const dashboardProjects=computed(()=>projects.value.map(project=>({...project,goal_label:goals.find(item=>item.key===project.goal_type)?.title||''})))
const firstTask=computed(()=>isAdapt.value?'改编策划师解析来源并提交 Adaptation Map 候选':'创意导演基于种子提交 3 个差异化 Story Core 候选')
const directiveTarget=computed(()=>mode.value==='focus'&&manuscript.value?{scope:'next_task' as const,target_type:'manuscript_unit' as const,target_id:manuscript.value.id,lifetime:'unit' as const,label:`第 ${manuscript.value.ordinal} ${isNovel.value?'章':'场'}`,reads:'当前正文、人物状态、相关伏笔'}:mode.value==='review'&&current.value?.task?{scope:'next_task' as const,target_type:'agent_task' as const,target_id:current.value.task.id,lifetime:'once' as const,label:`Agent Task #${current.value.task.id}`,reads:'原任务、交付候选、当前 Context Pack'}:{scope:'project_rule' as const,target_type:'project' as const,target_id:current.value?.id||null,lifetime:'project' as const,label:'整体项目',reads:'Story Core、创作章程、后续所有任务'})
const pendingDecisionCount=computed(()=>(current.value?.task?.candidates.filter(x=>x.status==='candidate').length||0)+(manuscript.value?.candidate&&manuscript.value.status!=='adopted'?1:0)+(manuscriptAiEdit.value?.status==='candidate'?1:0)+(revision.value?.status==='candidate'?1:0)+assetCandidates.value.filter(x=>x.status==='candidate').length+manuscriptImpactCandidates.value.filter(x=>x.status==='candidate').length+storyBibleChanges.value.filter(x=>x.status==='candidate').length+cascadeRevisions.value.filter(x=>x.status==='candidate').length)
const currentUnitLabel=computed(()=>currentStoryUnit.value?.title||(manuscript.value?`第 ${manuscript.value.ordinal} ${isNovel.value?'章':'场'}`:'作品规划'))
const agentWorkLabel=computed(()=>busy.value?'正在处理你的最新操作':current.value?.pulse?.needs_user?'已暂停，等待你的判断':current.value?.pulse?.headline||'等待你确定下一步')
const collaborationUnitState=computed<'adopted'|'candidate'|'planned'>(()=>currentStoryUnit.value?.status==='adopted'?'adopted':manuscript.value?.candidate?'candidate':'planned')
const handoffSummary=computed(()=>contextPreview.value?{characters:contextPreview.value.characters.length,relationships:contextPreview.value.relationships.length,openThreads:contextPreview.value.open_threads.length,previousTitle:contextPreview.value.previous_anchor?.title||'',warnings:contextPreview.value.warnings}:null)
function storyBibleChangeSummary(change:StoryBibleChange){return String(change.proposed.narrative_function||change.proposed.objective_relationship||change.proposed.dramatic_constraint||change.proposed.planting_method||'等待确认后进入后续创作')}
function begin(){step.value=1;screen.value='create';void router.push({name:'create-project'})}
async function openDashboardProject(project:{id:number}){const match=projects.value.find(item=>item.id===project.id);if(!match)return;const saved=localStorage.getItem(`scriptflow:last-project-route:${project.id}`);if(saved?.startsWith(`/projects/${project.id}/`)){await router.push(saved);return}await openProject(match)}
function spaceForMode(value:WorkspaceMode):WorkspaceSpace{return value==='focus'?'work':value==='blueprint'?'story':value==='plan'?'story':'review'}
function modeForSpace(value:unknown):WorkspaceMode{return value==='story'?'plan':value==='review'?'review':'focus'}
function currentGroupId(unitId:number|null|undefined){return storyMap.value?.groups.find(group=>group.units.some(unit=>unit.id===unitId))?.id}
async function syncWorkspaceRoute(replace=false){if(!current.value)return;const projectId=current.value.id,groupId=currentGroupId(currentStoryUnit.value?.id),unitId=currentStoryUnit.value?.id;const params:Record<string,string>={projectId:String(projectId),space:spaceForMode(mode.value)};if(groupId)params.groupId=String(groupId);if(unitId)params.unitId=String(unitId);const location={name:'workspace' as const,params};localStorage.setItem(`scriptflow:last-project-route:${projectId}`,router.resolve(location).fullPath);if(replace)await router.replace(location);else await router.push(location)}
async function switchMode(value:WorkspaceMode){if(mode.value==='focus'&&value!=='focus'&&!(await flushManuscriptSave())){error.value='正文尚未安全保存，暂不能离开作品空间';return}mode.value=value;await syncWorkspaceRoute()}
function next(){if(step.value<4)step.value++;else void createProject()}
function pickFile(event:Event){sourceFile.value=(event.target as HTMLInputElement).files?.[0]||null}
async function createProject(){busy.value=true;error.value='';try{const response=await fetch(`${API}/projects`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:title.value||'未命名作品',goal_type:goal.value,seed:seed.value,genre:genre.value,audience:audience.value,source_name:sourceName.value,source_type:isAdapt.value?(sourceMethod.value==='upload'?'file_reference':'pasted_text'):'none',source_content:isAdapt.value&&sourceMethod.value==='paste'?seed.value:'',source_file_name:sourceFile.value?.name||'',seed_maturity:seedMaturity.value,planning_mode:planningMode.value,medium_key:mediumKey.value,story_structure:storyStructure.value,target_volume_count:targetVolumeCount.value,target_chapter_count:targetChapterCount.value,target_episode_count:targetEpisodeCount.value,target_scenes_per_episode:targetScenesPerEpisode.value,target_words:targetWords.value,target_minutes_per_episode:targetMinutes.value,style_direction:styleDirection.value})});if(!response.ok)throw new Error('项目创建失败');current.value=await response.json();projects.value.unshift(current.value!);revision.value=null;manuscriptAiEdit.value=null;selectedText.value=null;manuscript.value=null;manuscriptDocument.value=null;manuscriptDraft.value='';manuscriptMetadata.value={};storyBibleChanges.value=[];cascadeRevisions.value=[];screen.value='workspace';mode.value='focus';railTab.value='collaboration';await loadProjectPlanning();await syncWorkspaceRoute(true);await runFirstTask()}catch(e){error.value=e instanceof Error?e.message:'项目创建失败'}finally{busy.value=false}}
async function refreshCurrent(){if(!current.value)return;const r=await fetch(`${API}/projects/${current.value.id}`);if(r.ok){const updated:Project=await r.json();current.value=updated;const index=projects.value.findIndex(p=>p.id===updated.id);if(index>=0)projects.value[index]=updated}}
async function runFirstTask(){if(!current.value?.task||current.value.task.status==='waiting_decision')return;busy.value=true;try{const r=await fetch(`${API}/projects/${current.value.id}/tasks/${current.value.task.id}/run`,{method:'POST'});if(!r.ok)throw new Error('Agent 任务执行失败');current.value.task=await r.json();await refreshCurrent();mode.value='review'}catch(e){error.value=e instanceof Error?e.message:'Agent 任务执行失败'}finally{busy.value=false}}
async function loadArchitecture(){if(!current.value)return;const r=await fetch(`${API}/projects/${current.value.id}/architecture`);if(r.ok)architecture.value=await r.json()}
async function planArchitecture(){if(!current.value)return;busy.value=true;error.value='';try{const r=await fetch(`${API}/projects/${current.value.id}/architecture/plan`,{method:'POST'});if(!r.ok)throw new Error('架构规划失败');architecture.value=await r.json();mode.value='plan'}catch(e){error.value=e instanceof Error?e.message:'架构规划失败'}finally{busy.value=false}}
async function loadContinuity(){if(!current.value?.adopted_story_core_id)return;const[continuityResponse,previewResponse]=await Promise.all([fetch(`${API}/projects/${current.value.id}/continuity`),fetch(`${API}/projects/${current.value.id}/continuity/next-context`)]);if(continuityResponse.ok)continuity.value=await continuityResponse.json();if(previewResponse.ok)contextPreview.value=await previewResponse.json()}
async function adopt(candidate:StoryCore){if(!current.value)return;busy.value=true;try{const r=await fetch(`${API}/projects/${current.value.id}/story-cores/${candidate.id}/adopt`,{method:'POST'});if(!r.ok)throw new Error('采用失败');current.value=await r.json();await Promise.all([loadContinuity(),loadArchitecture()]);mode.value='blueprint'}catch(e){error.value=e instanceof Error?e.message:'采用失败'}finally{busy.value=false}}
async function draftOpening(){if(!current.value)return;busy.value=true;error.value='';try{const selectedId=currentStoryUnit.value?.id;const suffix=selectedId?`?story_map_unit_id=${selectedId}`:'';const r=await fetch(`${API}/projects/${current.value.id}/manuscript/next${suffix}`,{method:'POST'});if(!r.ok)throw new Error('正文候选生成失败');manuscript.value=await r.json();chatHistory.value=[];await Promise.all([refreshCurrent(),loadProjectPlanning(),loadArchitecture()]);mode.value='focus'}catch(e){error.value=e instanceof Error?e.message:'正文候选生成失败'}finally{busy.value=false}}
async function adoptOpening(){if(!current.value||!manuscript.value?.candidate)return;busy.value=true;try{const r=await fetch(`${API}/projects/${current.value.id}/manuscript/${manuscript.value.candidate.id}/adopt`,{method:'POST'});if(!r.ok)throw new Error('正文采用失败');manuscript.value=await r.json();await Promise.all([loadContinuity(),refreshCurrent(),loadProjectPlanning(),loadManuscriptDocument(),loadArchitecture()])}catch(e){error.value=e instanceof Error?e.message:'正文采用失败'}finally{busy.value=false}}
async function requestRevision(){if(!current.value||!manuscript.value?.candidate||!feedbackText.value.trim())return;const txt=feedbackText.value.trim();chatHistory.value.push({role:'user',text:txt});feedbackText.value='';feedbackBusy.value=true;error.value='';try{const r=await fetch(`${API}/projects/${current.value.id}/manuscript/${manuscript.value.candidate.id}/revise`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({feedback:txt})});if(!r.ok)throw new Error('修改请求失败');const updated=await r.json();if(updated.candidate){chatHistory.value.push({role:'agent',content:updated.candidate.content,text:updated.candidate.title,candidateId:updated.candidate.id});manuscript.value=updated}await loadContinuity()}catch(e){error.value=e instanceof Error?e.message:'修改请求失败'}finally{feedbackBusy.value=false}}
async function adoptRevision(candidateId:number){if(!current.value)return;busy.value=true;try{const r=await fetch(`${API}/projects/${current.value.id}/manuscript/${candidateId}/adopt`,{method:'POST'});if(!r.ok)throw new Error('采用失败');manuscript.value=await r.json();chatHistory.value=[];await Promise.all([loadContinuity(),refreshCurrent(),loadProjectPlanning(),loadManuscriptDocument(),loadArchitecture()])}catch(e){error.value=e instanceof Error?e.message:'采用失败'}finally{busy.value=false}}
function captureSelection(event:Event){const target=event.target as HTMLTextAreaElement;selectedText.value=selectionFromRange(target.value,target.selectionStart,target.selectionEnd);if(selectedText.value)replacementText.value=selectedText.value.text}
async function createManuscriptAiEdit(){if(!current.value||!manuscript.value||!manuscriptDocument.value||!selectedText.value)return;if(!(await flushManuscriptSave())){error.value='请先完成正文保存再调用 AI 编辑';return}busy.value=true;error.value='';aiEditStreamingText.value='';aiEditAbortController=new AbortController();try{const r=await fetch(`${API}/projects/${current.value.id}/manuscript/units/${manuscript.value.id}/ai-edits/stream`,{method:'POST',headers:{'Content-Type':'application/json'},signal:aiEditAbortController.signal,body:JSON.stringify({base_version:manuscriptDocument.value.version,selection_start:selectedText.value.start,selection_end:selectedText.value.end,selected_text:selectedText.value.text,mode:aiEditMode.value,instruction:aiEditInstruction.value.trim(),preserve:['选区外正文','已采用事实','人物语气']})});if(!r.ok){const detail=await r.json().catch(()=>null);throw new Error(detail?.detail||'AI 局部编辑失败')}if(!r.body)throw new Error('浏览器不支持流式候选');await consumeNdjson(r.body,event=>{if(event.type==='delta')aiEditStreamingText.value+=String(event.text||'');if(event.type==='candidate')manuscriptAiEdit.value=event.revision as ManuscriptAiEdit})}catch(e){if(e instanceof DOMException&&e.name==='AbortError'){aiEditStreamingText.value='';return}error.value=e instanceof Error?e.message:'AI 局部编辑失败'}finally{busy.value=false;aiEditAbortController=undefined}}
function cancelManuscriptAiEditStream(){aiEditAbortController?.abort()}
async function resolveManuscriptAiEdit(action:'adopt'|'reject',keepSelection=false){if(!current.value||!manuscriptAiEdit.value)return;busy.value=true;error.value='';try{const r=await fetch(`${API}/projects/${current.value.id}/manuscript/ai-edits/${manuscriptAiEdit.value.id}/${action}`,{method:'POST'});if(r.status===409){manuscriptAiEdit.value={...manuscriptAiEdit.value,status:'stale',stale_reason:'正文版本已变化，请重新选择后生成'};return}if(!r.ok)throw new Error('局部修改处理失败');manuscriptAiEdit.value=await r.json();if(action==='adopt'){await Promise.all([loadManuscriptDocument(),loadManuscriptImpactCandidates()]);if(manuscript.value)manuscript.value.adopted_content=manuscriptDraft.value;selectedText.value=null}else if(keepSelection){manuscriptAiEdit.value=null}}catch(e){error.value=e instanceof Error?e.message:'局部修改处理失败'}finally{busy.value=false}}
function restartManuscriptAiEdit(){manuscriptAiEdit.value=null;selectedText.value=null;aiEditInstruction.value=''}
async function createSelectionRevision(){if(!current.value||!manuscript.value?.scene_id||!selectedText.value||!revisionInstruction.value.trim()||!replacementText.value.trim())return;busy.value=true;error.value='';try{const payload=revisionPayload(manuscript.value.adopted_content,selectedText.value,revisionInstruction.value,replacementText.value);const r=await fetch(`${API}/projects/${current.value.id}/revisions`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scene_id:manuscript.value.scene_id,...payload})});if(!r.ok)throw new Error('Revision 候选创建失败');revision.value=await r.json();await loadAssetCandidates()}catch(e){error.value=e instanceof Error?e.message:'Revision 候选创建失败'}finally{busy.value=false}}
async function resolveSelectionRevision(action:'adopt'|'reject'){if(!current.value||!revision.value)return;busy.value=true;error.value='';try{const r=await fetch(`${API}/projects/${current.value.id}/revisions/${revision.value.id}/${action}`,{method:'POST'});if(r.status===409){revision.value={...revision.value,status:'stale',stale_reason:'基线内容已变化，请重新比较'};return}if(!r.ok)throw new Error(action==='adopt'?'采用 Revision 失败':'拒绝 Revision 失败');const resolved:CreativeRevision=await r.json();revision.value=resolved;if(action==='adopt'&&manuscript.value)manuscript.value.adopted_content=resolved.candidate_content}catch(e){error.value=e instanceof Error?e.message:'Revision 处理失败'}finally{busy.value=false}}
async function restartSelectionRevision(){revision.value=null;selectedText.value=null;revisionInstruction.value='';replacementText.value='';if(current.value){const r=await fetch(`${API}/projects/${current.value.id}/manuscript/latest`);if(r.ok)manuscript.value=await r.json()}}
async function loadMediums(){try{const r=await fetch(`${API}/mediums`);if(r.ok)mediums.value=await r.json()}catch{}}
async function loadStructures(){try{const r=await fetch(`${API}/structures`);if(r.ok)structures.value=await r.json()}catch{}}
async function loadRuntime(){try{const r=await fetch(`${API}/runtime/status`);if(r.ok)runtime.value=await r.json()}catch{}}
async function loadDirectives(){if(!current.value)return;const r=await fetch(`${API}/projects/${current.value.id}/directives`);if(r.ok)directives.value=await r.json()}
async function loadAssetCandidates(){if(!current.value)return;const r=await fetch(`${API}/projects/${current.value.id}/living-asset-candidates`);if(r.ok)assetCandidates.value=await r.json()}
async function loadManuscriptImpactCandidates(){if(!current.value)return;const r=await fetch(`${API}/projects/${current.value.id}/manuscript-impact-candidates`);if(r.ok)manuscriptImpactCandidates.value=await r.json()}
async function loadStoryBibleChanges(){if(!current.value)return;const r=await fetch(`${API}/projects/${current.value.id}/story-bible/changes`);if(r.ok)storyBibleChanges.value=await r.json()}
async function loadCascadeRevisions(){if(!current.value)return;const r=await fetch(`${API}/projects/${current.value.id}/cascade-revisions`);if(r.ok)cascadeRevisions.value=await r.json()}
async function loadProjectPlanning(){if(!current.value)return;const selectedId=currentStoryUnit.value?.id;const planResponse=await fetch(`${API}/projects/${current.value.id}/plan`);if(planResponse.ok){projectPlan.value=await planResponse.json();planVolumeCount.value=Math.max(projectPlan.value?.target_volume_count||1,1);planChapterCount.value=Math.max(projectPlan.value?.target_chapter_count||1,1);planEpisodeCount.value=Math.max(projectPlan.value?.target_episode_count||1,1);planScenesPerEpisode.value=Math.max(projectPlan.value?.target_scenes_per_episode||1,1)}const mapResponse=await fetch(`${API}/projects/${current.value.id}/story-map`);if(mapResponse.ok){storyMap.value=await mapResponse.json();const units=storyMap.value?.groups.flatMap(group=>group.units)||[];currentStoryUnit.value=units.find(unit=>unit.id===selectedId)||units[0]||null}}
async function loadManuscriptDocument(){if(!current.value||!manuscript.value||manuscript.value.status!=='adopted'){manuscriptDocument.value=null;manuscriptDraft.value='';manuscriptMetadata.value={};manuscriptVersions.value=[];manuscriptSaveStatus.value='idle';return}const base=`${API}/projects/${current.value.id}/manuscript/units/${manuscript.value.id}/document`;const r=await fetch(base);if(r.ok){manuscriptDocument.value=await r.json();manuscriptDraft.value=manuscriptDocument.value?.content||'';manuscriptMetadata.value=manuscriptDocument.value?.metadata||{};const versions=await fetch(`${base}/versions`);manuscriptVersions.value=versions.ok?await versions.json():[];manuscriptSaveStatus.value='idle'}else{manuscriptSaveStatus.value='failed'}}
async function flushManuscriptSave(){if(manuscriptSaveTimer){clearTimeout(manuscriptSaveTimer);manuscriptSaveTimer=undefined}if(manuscriptSaveStatus.value!=='dirty')return manuscriptSaveStatus.value!=='conflict'&&manuscriptSaveStatus.value!=='failed';if(!current.value||!manuscript.value||!manuscriptDocument.value)return false;manuscriptSaveStatus.value='saving';try{const base=`${API}/projects/${current.value.id}/manuscript/units/${manuscript.value.id}/document`;const r=await fetch(base,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({base_version:manuscriptDocument.value.version,content:manuscriptDraft.value,metadata:manuscriptMetadata.value})});if(r.status===409){manuscriptSaveStatus.value='conflict';return false}if(!r.ok)throw new Error('正文保存失败');manuscriptDocument.value=await r.json();manuscriptMetadata.value=manuscriptDocument.value?.metadata||{};manuscript.value.adopted_content=manuscriptDraft.value;const versions=await fetch(`${base}/versions`);if(versions.ok)manuscriptVersions.value=await versions.json();manuscriptSaveStatus.value='saved';return true}catch{manuscriptSaveStatus.value='failed';return false}}
function updateManuscriptDraft(content:string){manuscriptDraft.value=content;manuscriptSaveStatus.value='dirty';if(manuscriptSaveTimer)clearTimeout(manuscriptSaveTimer);manuscriptSaveTimer=setTimeout(()=>{void flushManuscriptSave()},800)}
function updateManuscriptMetadata(metadata:ManuscriptMetadata){manuscriptMetadata.value=metadata;updateManuscriptDraft(manuscriptDraft.value)}
async function restoreManuscriptVersion(version:number){if(!current.value||!manuscript.value||!manuscriptDocument.value||!(await flushManuscriptSave()))return;busy.value=true;error.value='';try{const r=await fetch(`${API}/projects/${current.value.id}/manuscript/units/${manuscript.value.id}/document/restore`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({base_version:manuscriptDocument.value.version,restore_version:version})});if(r.status===409){manuscriptSaveStatus.value='conflict';return}if(!r.ok)throw new Error('正文版本恢复失败');await loadManuscriptDocument();manuscript.value.adopted_content=manuscriptDraft.value;selectedText.value=null;manuscriptAiEdit.value=null}catch(e){error.value=e instanceof Error?e.message:'正文版本恢复失败'}finally{busy.value=false}}
async function selectStoryUnit(unit:StoryMapUnit,syncRoute=true){if(!(await flushManuscriptSave())){error.value='当前正文尚未安全保存，请先处理保存状态';return}currentStoryUnit.value=unit;revision.value=null;manuscriptAiEdit.value=null;selectedText.value=null;if(!current.value)return;if(unit.manuscript_unit_id){const r=await fetch(`${API}/projects/${current.value.id}/manuscript/units/${unit.manuscript_unit_id}`);if(r.ok)manuscript.value=await r.json()}else manuscript.value=null;await loadManuscriptDocument();if(syncRoute)await syncWorkspaceRoute()}
function beginStoryUnitEdit(unit:StoryMapUnit){editingStoryUnitId.value=unit.id;storyUnitTitle.value=unit.title;storyUnitIntent.value=unit.intent}
function cancelStoryUnitEdit(){editingStoryUnitId.value=null;storyUnitTitle.value='';storyUnitIntent.value=''}
async function saveStoryUnit(){if(!current.value||!editingStoryUnitId.value||!storyUnitTitle.value.trim())return;busy.value=true;error.value='';try{const r=await fetch(`${API}/projects/${current.value.id}/story-map/units/${editingStoryUnitId.value}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:storyUnitTitle.value.trim(),intent:storyUnitIntent.value.trim()})});if(!r.ok)throw new Error('目录单元保存失败');const updated:StoryMapUnit=await r.json();if(storyMap.value)for(const group of storyMap.value.groups){const index=group.units.findIndex(unit=>unit.id===updated.id);if(index>=0)group.units[index]=updated}if(currentStoryUnit.value?.id===updated.id)currentStoryUnit.value=updated;cancelStoryUnitEdit()}catch(e){error.value=e instanceof Error?e.message:'目录单元保存失败'}finally{busy.value=false}}
async function addStoryUnit(group:StoryMapGroup){if(!current.value)return;busy.value=true;error.value='';try{const next=group.units.length+1;const title=isNovel.value?`第 ${storyMap.value?.planned_units?storyMap.value.planned_units+1:next} 章 · 待规划`:`Scene ${next} · 待规划`;const r=await fetch(`${API}/projects/${current.value.id}/story-map/groups/${group.id}/units`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,intent:'',target_length:0})});if(!r.ok)throw new Error('新增目录单元失败');const added:StoryMapUnit=await r.json();await loadProjectPlanning();await selectStoryUnit(added);beginStoryUnitEdit(added)}catch(e){error.value=e instanceof Error?e.message:'新增目录单元失败'}finally{busy.value=false}}
async function moveStoryUnit(group:StoryMapGroup,unit:StoryMapUnit,direction:-1|1){if(!current.value||busy.value)return;const index=group.units.findIndex(item=>item.id===unit.id),target=index+direction;if(index<0||target<0||target>=group.units.length)return;const ordered=group.units.map(item=>item.id);[ordered[index],ordered[target]]=[ordered[target],ordered[index]];busy.value=true;error.value='';try{const r=await fetch(`${API}/projects/${current.value.id}/story-map/groups/${group.id}/order`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({ordered_unit_ids:ordered})});if(!r.ok)throw new Error('目录排序失败');storyMap.value=await r.json();currentStoryUnit.value=storyMap.value?.groups.flatMap(item=>item.units).find(item=>item.id===unit.id)||unit}catch(e){error.value=e instanceof Error?e.message:'目录排序失败'}finally{busy.value=false}}
function planScalePayload(confirm_rebuild=false){return projectPlan.value?.delivery_medium==='novel'?{target_volume_count:planVolumeCount.value,target_chapter_count:planChapterCount.value,confirm_rebuild}:{target_episode_count:planEpisodeCount.value,target_scenes_per_episode:planScenesPerEpisode.value,confirm_rebuild}}
async function previewPlanScale(){if(!current.value)return;busy.value=true;error.value='';try{const r=await fetch(`${API}/projects/${current.value.id}/plan/impact`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(planScalePayload())});if(!r.ok)throw new Error('无法计算规模调整影响');planImpact.value=await r.json()}catch(e){error.value=e instanceof Error?e.message:'无法计算规模调整影响'}finally{busy.value=false}}
async function applyPlanScale(){if(!current.value||!planImpact.value?.can_apply)return;busy.value=true;error.value='';try{const r=await fetch(`${API}/projects/${current.value.id}/plan`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(planScalePayload(true))});if(!r.ok){const detail=await r.json().catch(()=>null);throw new Error(detail?.detail||'规模调整未能应用')}projectPlan.value=await r.json();planImpact.value=null;currentStoryUnit.value=null;manuscript.value=null;await loadProjectPlanning()}catch(e){error.value=e instanceof Error?e.message:'规模调整未能应用'}finally{busy.value=false}}
async function resolveAssetCandidate(candidate:LivingAssetCandidate,action:'adopt'|'reject'){if(!current.value)return;busy.value=true;try{const r=await fetch(`${API}/projects/${current.value.id}/living-asset-candidates/${candidate.id}/${action}`,{method:'POST'});if(!r.ok)throw new Error('作品变化处理失败');const resolved:LivingAssetCandidate=await r.json();const index=assetCandidates.value.findIndex(item=>item.id===resolved.id);if(index>=0)assetCandidates.value[index]=resolved}catch(e){error.value=e instanceof Error?e.message:'作品变化处理失败'}finally{busy.value=false}}
async function resolveManuscriptImpact(candidate:ManuscriptImpactCandidate,action:'adopt'|'reject'){if(!current.value)return;busy.value=true;error.value='';try{const r=await fetch(`${API}/projects/${current.value.id}/manuscript-impact-candidates/${candidate.id}/${action}`,{method:'POST'});if(!r.ok){const detail=await r.json().catch(()=>null);throw new Error(detail?.detail||'正文影响处理失败')}const resolved:ManuscriptImpactCandidate=await r.json();const index=manuscriptImpactCandidates.value.findIndex(item=>item.id===resolved.id);if(index>=0)manuscriptImpactCandidates.value[index]=resolved;if(action==='adopt')await loadContinuity()}catch(e){error.value=e instanceof Error?e.message:'正文影响处理失败'}finally{busy.value=false}}
async function createLedgerEntity(){/* ... */ if(!current.value||!newEntityName.value.trim())return;busy.value=true;try{if(newEntityType.value==='character'){const r=await fetch(`${API}/projects/${current.value.id}/story-bible/character-introductions`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:newEntityName.value.trim(),identity:newEntityIdentity.value.trim(),narrative_function:newCharacterFunction.value.trim(),voice:newCharacterVoice.value.trim(),first_appearance_ordinal:newCharacterFirstOrdinal.value})});if(!r.ok)throw new Error('角色创建失败');await loadStoryBibleChanges();railTab.value='decisions'}else{const r=await fetch(`${API}/projects/${current.value.id}/entities`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({entity_type:newEntityType.value,name:newEntityName.value.trim(),identity:newEntityIdentity.value.trim()})});if(!r.ok)throw new Error('组织创建失败');await loadContinuity()}newEntityName.value='';newEntityIdentity.value=''}catch(e){error.value=e instanceof Error?e.message:'创建失败'}finally{busy.value=false}}
async function openProject(p:Project,syncRoute=true){current.value=p;title.value=p.title;goal.value=p.goal_type;seed.value=p.seed;continuity.value=null;manuscript.value=null;manuscriptDocument.value=null;manuscriptDraft.value='';manuscriptSaveStatus.value='idle';revision.value=null;manuscriptAiEdit.value=null;selectedText.value=null;directives.value=[];assetCandidates.value=[];manuscriptImpactCandidates.value=[];storyBibleChanges.value=[];cascadeRevisions.value=[];projectPlan.value=null;storyMap.value=null;currentStoryUnit.value=null;editingStoryUnitId.value=null;planImpact.value=null;railTab.value='collaboration';directiveNotice.value='';screen.value='workspace';await Promise.all([loadArchitecture(),loadDirectives(),loadAssetCandidates(),loadManuscriptImpactCandidates(),loadStoryBibleChanges(),loadCascadeRevisions(),loadProjectPlanning()]);if(p.adopted_story_core_id){await loadContinuity();const r=await fetch(`${API}/projects/${p.id}/manuscript/latest`);if(r.ok){manuscript.value=await r.json();const loadedStoryMap=storyMap.value as StoryMap|null;const matchingUnit=loadedStoryMap?.groups.flatMap((group:StoryMapGroup)=>group.units).find((unit:StoryMapUnit)=>unit.manuscript_unit_id===manuscript.value?.id);if(matchingUnit)currentStoryUnit.value=matchingUnit;await loadManuscriptDocument()}}if(syncRoute)await syncWorkspaceRoute()}
async function reset(){if(!(await flushManuscriptSave())){error.value='正文尚未安全保存，暂不能返回项目列表';return}title.value='';seed.value='';sourceName.value='';step.value=1;current.value=null;storyMap.value=null;currentStoryUnit.value=null;manuscript.value=null;manuscriptDocument.value=null;screen.value='dashboard';await router.push({name:'dashboard'})}
async function restoreFromRoute(){if(route.name==='create-project'){screen.value='create';return}if(route.name!=='workspace'){screen.value='dashboard';return}if(!projectsLoaded.value)return;const projectId=Number(route.params.projectId),project=projects.value.find(item=>item.id===projectId);if(!project){await router.replace({name:'dashboard'});return}mode.value=modeForSpace(route.params.space);if(current.value?.id!==projectId)await openProject(project,false);const unitId=Number(route.params.unitId),unit=storyMap.value?.groups.flatMap(group=>group.units).find(item=>item.id===unitId);if(unit&&currentStoryUnit.value?.id!==unit.id)await selectStoryUnit(unit,false)}
watch(()=>route.fullPath,()=>{if(projectsLoaded.value)void restoreFromRoute()})
function protectUnsavedManuscript(event:BeforeUnloadEvent){if(manuscriptSaveStatus.value==='dirty'||manuscriptSaveStatus.value==='saving'){event.preventDefault();event.returnValue=''}}
onMounted(async()=>{window.addEventListener('beforeunload',protectUnsavedManuscript);await Promise.all([loadRuntime(),loadMediums(),loadStructures()]);try{const r=await fetch(`${API}/projects`);if(r.ok)projects.value=await r.json()}catch{}projectsLoaded.value=true;await restoreFromRoute()})
onBeforeUnmount(()=>{window.removeEventListener('beforeunload',protectUnsavedManuscript);if(manuscriptSaveTimer)clearTimeout(manuscriptSaveTimer)})
</script>

<template>
<main>
 <header class="top"><strong>ScriptFlow</strong>
 <nav v-if="screen==='workspace'"><button v-for="m in tabDefs" :key="m.k" :class="{active:mode===m.k}" @click="switchMode(m.k)">{{m.n}}</button></nav>
 <div class="phase-indicator" v-if="screen==='workspace'">▶ {{currentPhase==='review'?'决策':currentPhase==='blueprint'?'规划':'创作'}}</div>
 <button v-if="screen!=='dashboard'" class="quiet" @click="reset">返回项目</button>
 <span :class="['runtime-pill',runtime?.mode]"><i></i>{{runtime?.capability_tier||'引擎连接中'}}</span></header>
 <DashboardPage v-if="screen==='dashboard'" :projects="dashboardProjects" @create="begin" @open="openDashboardProject"/>

 <form v-if="screen==='create'" class="wizard">
 <header><strong>ScriptFlow</strong><button type="button" class="quiet" @click="reset">返回</button></header>
 <div class="steps"><span v-for="s in 4" :key="s" :class="{active:step>=s}">{{s}}</span></div>
 <h1 v-if="step===1">你想让什么作品长出来？</h1>
 <template v-if="step===1">
  <button type="button" class="goal-card" v-for="g in goals" :key="g.key" :class="{selected:goal===g.key}" @click="goal=g.key"><strong>{{g.title}}</strong><small>{{g.desc}}</small></button>
 </template>
 <template v-if="step===2">
  <h1>先给团队一颗种子</h1>
  <label>项目名称 <input v-model="title" placeholder="给作品一个名字" /></label>
  <template v-if="isAdapt">
   <div class="source-controls">
    <button type="button" :class="{active:sourceMethod==='paste'}" @click="sourceMethod='paste'">粘贴文本</button>
    <button type="button" :class="{active:sourceMethod==='upload'}" @click="sourceMethod='upload'">上传文件</button>
    <button type="button" :class="{active:sourceMethod==='later'}" @click="sourceMethod='later'">稍后添加</button>
   </div>
   <template v-if="sourceMethod==='paste'">
    <label>来源名称 <input v-model="sourceName" placeholder="原著名称" /></label>
    <label>来源文本 <textarea v-model="seed" rows="8" placeholder="粘贴小说、剧本或故事原文..." /></label>
   </template>
   <template v-if="sourceMethod==='upload'">
    <label>来源名称 <input v-model="sourceName" placeholder="原著名称" /></label>
    <label>上传来源文件 <input type="file" accept=".txt,.md,.pdf,.docx" @change="pickFile" /></label>
    <small v-if="sourceFile" style="color:var(--accent)">已选择: {{sourceFile.name}}</small>
    <label>或者粘贴片段 <textarea v-model="seed" rows="4" placeholder="粘贴关键章节或梗概..." /></label>
   </template>
   <template v-if="sourceMethod==='later'">
    <small style="color:var(--t4)">可以先写一段梗概，来源材料稍后在项目设置中添加</small>
    <label>梗概 / 核心片段 <textarea v-model="seed" rows="6" placeholder="写一段梗概或关键场景帮助 Agent 理解方向..." /></label>
   </template>
  </template>
  <template v-else>
   <label>主题 / 灵感 / 梗概 / 草稿 <textarea v-model="seed" rows="6" placeholder="随意写下一句话、一段对话、一个场景..." /></label>
  </template>
 </template>
 <template v-if="step===3">
  <h1>设定创作基调</h1>
  <label>题材 <select v-model="genre"><option v-for="g in ['悬疑','都市','古装','科幻','言情','喜剧','奇幻','现实','其他']" :key="g" :value="g">{{g}}</option></select></label>
  <label>目标受众 <select v-model="audience"><option v-for="a in ['大众','女频','男频','青少年','文艺','悬疑爱好者']" :key="a" :value="a">{{a}}</option></select></label>
  <label>创作媒介 <select v-model="mediumKey"><option v-if="!mediums.length" value="" disabled>加载中…</option><option v-for="m in mediums" :key="m.key" :value="m.key">{{m.label}}</option></select></label>
  <template v-if="mediumKey!=='novel'&&mediumKey!=='short-story'">
   <label>目标集数 <input type="number" v-model.number="targetEpisodeCount" min="1" max="200" /></label>
   <label>每集场数 <input type="number" v-model.number="targetScenesPerEpisode" min="1" max="50" /></label>
   <label>单集目标时长(分钟) <input type="number" v-model.number="targetMinutes" min="1" max="180" /></label>
  </template>
  <label>叙事结构 <select v-model="storyStructure"><option v-if="!structures.length" value="" disabled>加载中…</option><option v-for="s in structures" :key="s.key" :value="s.key">{{s.label}} — {{s.description}}</option></select><small style="margin-top:2px;color:var(--t4)">{{structures.find(s=>s.key===storyStructure)?.best_for||''}}</small></label>
<label>风格方向 <small>(选填)</small> <input v-model="styleDirection" placeholder="如 冷峻克制、黑色幽默、温暖治愈" /></label>
 </template>
 <template v-if="step===4">
  <h1>确认创作计划</h1>
  <div class="confirm"><div><small>创作类型</small><strong>{{goalLabel}}</strong></div><div><small>媒介</small><strong>{{mediums.find(m=>m.key===mediumKey)?.label||mediumKey}}</strong></div><div><small>题材</small><strong>{{genre}}</strong></div><template v-if="mediumKey!=='novel'&&mediumKey!=='short-story'"><div><small>集数</small><strong>{{targetEpisodeCount}}集 × {{targetScenesPerEpisode}}场 · {{targetMinutes}}分钟/集</strong></div></template></div>
  <p class="hint">创建后会先形成可编辑作品目录，不会立即无限生成正文。</p>
 </template>
 <footer><button type="button" class="secondary" :disabled="step===1" @click="step--">上一步</button><button type="button" class="primary" @click="next">{{step===4?'创建并启动首个任务':'继续'}}</button></footer>
</form>

 <article class="paper blueprint" v-if="screen==='workspace'&&mode==='blueprint'">
   <small>作品蓝图</small>
   <template v-if="architecture?.status==='planned'">
    <div class="plan-heading"><div><h1>{{architecture.thesis}}</h1><p>{{architecture.approach}}</p></div></div>
    <div class="arc-timeline">
     <div v-for="arc in architecture.arcs" :key="arc.id" class="arc-card">
      <div class="arc-range">EP{{arc.episode_start}}-{{arc.episode_end}} · {{arc.episode_end - arc.episode_start + 1}}集</div>
      <h3>{{arc.title}}</h3>
      <p>{{arc.core_conflict}}</p>
      <div class="arc-details"><span>🎭 {{arc.protag_state}}</span><span>⚔️ {{arc.antag_state}}</span><span>💫 {{arc.emotional_landing}}</span></div>
      <details><summary>关键事件 ({{arc.must_have_events.length}})</summary><ul><li v-for="event in arc.must_have_events" :key="event">{{event}}</li></ul></details>
      <details><summary>伏笔安排 ({{arc.foreshadow_actions.length}})</summary><ul><li v-for="fa in arc.foreshadow_actions" :key="fa">{{fa}}</li></ul></details>
     </div>
    </div>
   </template>
   <template v-else><h1>故事蓝图等待绘制</h1><p>采用 StoryCore 后，让架构规划师为你绘制全局叙事蓝图。</p><button class="primary" :disabled="busy" @click="planArchitecture">{{busy?'规划师正在工作…':'绘制全局蓝图'}}</button></template>
 </article>

 <div class="workspace-layout" v-if="screen==='workspace'&&mode!=='blueprint'">
  <aside class="catalog-panel">
   <div v-if="storyMap" class="story-tree">
    <div v-for="g in storyMap.groups" :key="g.id" class="story-group">
     <strong>{{g.title||'第'+g.ordinal+'集'}}</strong>
     <div v-for="u in g.units" :key="u.id" :class="['story-unit',{active:currentStoryUnit?.id===u.id,adopted:u.status==='adopted'}]" @click="selectStoryUnit(u)">
      <span class="unit-label">{{u.title||('Scene '+u.ordinal)}}</span>
      <span class="unit-status">{{u.status==='adopted'?'✓':u.status==='drafting'?'…':'·'}}</span>
     </div>
    </div>
   </div>
  </aside>
  <section class="center-panel">
   <header><span>{{agentWorkLabel}}</span></header>
   <article v-if="mode==='focus'" class="paper work">
    <div v-if="manuscript?.candidate" class="agent-chat">
    <div class="chat-msg agent">
     <div class="msg-header">🤖 写作者 · {{manuscript.candidate.title}}</div>
     <div class="msg-body"><pre>{{manuscript.candidate.content}}</pre></div>
     <div class="msg-actions">
      <button class="primary" :disabled="busy" @click="adoptOpening">采用此稿</button>
     </div>
    </div>
    <div v-for="(msg,i) in chatHistory" :key="i" :class="['chat-msg',msg.role]">
     <div class="msg-header">{{msg.role==='user'?'👤 你':'🤖 写作者'}}</div>
     <div class="msg-body" v-if="msg.content"><pre>{{msg.content}}</pre></div>
     <div class="msg-body" v-else><p>{{msg.text}}</p></div>
     <div class="msg-actions" v-if="msg.role==='agent'&&msg.candidateId">
      <button class="primary" :disabled="busy" @click="adoptRevision(msg.candidateId)">采用此版</button>
     </div>
    </div>
    <div class="chat-input-row">
     <input v-model="feedbackText" placeholder="告诉写作者——'开头太慢' '这段对话太冷' '换到白天场景'…" @keyup.enter="requestRevision" />
     <button class="primary" :disabled="feedbackBusy||!feedbackText.trim()" @click="requestRevision">{{feedbackBusy?'…':'发送'}}</button>
    </div>
   </div>
    <template v-else-if="currentStoryUnit"><h2>{{currentStoryUnit.title||'待规划'}}</h2><p>点击下方为当前单元生成正文候选</p><button class="primary" :disabled="busy" @click="draftOpening">{{busy?'写作者正在创作…':'生成正文候选'}}</button></template>
    <template v-else><p>请在左侧目录选择一个单元</p></template>
   </article>
   <article class="paper planning" v-else-if="mode==='plan'">
    <template v-if="continuity">
     <section class="story-section">
      <h3>🎭 角色小传</h3>
      <div class="entity-cards">
       <div v-for="e in continuity.entities" :key="e.id" class="entity-card">
        <h4>{{e.name}} <small>{{e.entity_type==='character'?'角色':e.entity_type}}</small></h4>
        <dl>
         <template v-if="e.truth"><dt>身份</dt><dd>{{e.truth.identity||e.truth.narrative_function||'—'}}</dd></template>
         <template v-if="e.truth && e.truth.voice"><dt>声音</dt><dd>{{e.truth.voice}}</dd></template>
         <template v-if="e.current_state"><dt>当前状态</dt><dd>{{JSON.stringify(e.current_state,null,2)}}</dd></template>
        </dl>
       </div>
      </div>
     </section>
     <section class="story-section" v-if="continuity.threads.length">
      <h3>🧵 故事线索</h3>
      <div v-for="t in continuity.threads" :key="t.id" class="thread-item">
       <strong>{{t.title}}</strong>
       <span class="tag">{{t.status}}</span>
       <p v-if="t.setup">{{t.setup}}</p>
       <small v-if="t.payoff_target">回收目标: {{t.payoff_target}}</small>
      </div>
     </section>
    </template>
    <template v-if="architecture?.status==='planned'">
     <section class="story-section">
      <h3>📐 叙事弧线</h3>
      <p><em>{{architecture.thesis}}</em></p>
      <div v-for="arc in architecture.arcs" :key="arc.id" class="arc-mini">
       <strong>{{arc.title}}</strong> <small>EP{{arc.episode_start}}-{{arc.episode_end}}</small>
       <p>{{arc.core_conflict}}</p>
       <p class="emotion">💫 {{arc.emotional_landing}}</p>
      </div>
     </section>
    </template>
    <p v-if="!continuity&&!architecture">还没有作品状态数据——先采用 StoryCore 并绘制蓝图</p>
   </article>
   <article class="paper review" v-else-if="mode==='review'">
    <small>决策清单</small>
    <div v-if="current?.task?.candidates?.filter((c:StoryCore)=>c.status==='candidate').length">
     <div v-for="c in current!.task!.candidates.filter((c:StoryCore)=>c.status==='candidate')" :key="c.id" class="candidate-card">
      <h3>{{c.title}}</h3><p>{{c.logline}}</p>
      <button class="primary" :disabled="busy" @click="adopt(c)">采用</button>
     </div>
    </div>
    <p v-else>暂无待处理决策</p>
   </article>
  </section>
  <aside class="rail-panel">
   <div v-if="continuity" class="rail-section">
    <h4>角色状态</h4>
    <div v-for="e in continuity.entities.slice(0,5)" :key="e.id" class="rail-entity">
     <strong>{{e.name}}</strong>
     <span class="rail-tag">{{e.frozen?'已定':'活跃'}}</span>
     <p v-if="e.current_state">{{Object.values(e.current_state).slice(0,2).join('·')||'—'}}</p>
    </div>
    <p v-if="continuity.entities.length>5" style="font-size:10px;color:var(--t4)">+{{continuity.entities.length-5}} 更多</p>
   </div>
   <div v-if="continuity?.threads.length" class="rail-section">
    <h4>伏笔线索</h4>
    <div v-for="t in continuity.threads.slice(0,3)" :key="t.id" class="rail-thread">
     <span :class="['dot',t.status]"></span>
     <span>{{t.title}}</span>
    </div>
   </div>
   <div v-if="continuity?.alerts.length" class="rail-section">
    <h4>连续性提醒</h4>
    <div v-for="a in continuity.alerts.slice(0,3)" :key="a.id" class="rail-alert">
     <span :class="['severity',a.severity]"></span>
     <span>{{a.message}}</span>
    </div>
   </div>
   <div v-if="contextPreview" class="rail-section">
    <h4>下一场上下文</h4>
    <p><strong>上一场:</strong> {{contextPreview.previous_anchor?.title||'无'}}</p>
    <p><strong>角色:</strong> {{contextPreview.characters.map((c:any)=>c.name).join(', ')||'—'}}</p>
    <div v-if="contextPreview.warnings.length"><p v-for="w in contextPreview.warnings" :key="w" class="rail-warning">⚠ {{w}}</p></div>
   </div>
  </aside>
 </div>
</main>
</template>

<style>
:root{--bg-root:#0a0a0b;--bg-surface:#161618;--border:rgba(255,255,255,0.08);--accent:#7170ff;--t1:#f7f8f8;--t2:#d0d6e0;--t3:#8a8f98;--t4:#62666d}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:Inter,system-ui,sans-serif;background:var(--bg-root);color:var(--t2);font-size:13px;-webkit-font-smoothing:antialiased}
button{cursor:pointer;font-family:inherit;font-size:inherit;border:none;background:none;color:inherit}
.top{display:flex;align-items:center;gap:12px;padding:0 16px;height:44px;background:rgba(255,255,255,0.02);border-bottom:1px solid var(--border);flex-shrink:0}
.top strong{font-size:15px;color:var(--t1)}.top nav{display:flex;gap:4px}.top nav button{padding:4px 12px;border-radius:6px;font-size:12px;color:var(--t3);transition:all .12s}.top nav button.active,.top nav button:hover{background:rgba(255,255,255,0.06);color:var(--t1)}.quiet{margin-left:auto;font-size:12px;color:var(--t4);padding:4px 8px;border-radius:4px}.quiet:hover{color:var(--t1)}
.runtime-pill{display:flex;align-items:center;gap:6px;font-size:10px;padding:2px 8px;border-radius:4px;background:rgba(255,255,255,0.04);color:var(--t4)}.runtime-pill i{width:5px;height:5px;border-radius:50%;background:var(--accent);animation:pulse 2s infinite}@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.primary{margin-top:12px;padding:8px 16px;border-radius:6px;font-size:13px;font-weight:590;background:var(--accent);color:#fff}.primary:disabled{opacity:.4}
.secondary{padding:8px 16px;border-radius:6px;font-size:13px;border:1px solid var(--border);color:var(--t3);background:transparent}
.blueprint .arc-timeline{display:flex;flex-direction:column;gap:16px;margin-top:20px}
.arc-card{background:var(--bg-surface);border:1px solid var(--border);border-radius:8px;padding:16px}.arc-range{font-size:11px;color:var(--accent);font-weight:590;margin-bottom:6px}.arc-card h3{font-size:16px;margin-bottom:6px}.arc-card p{font-size:13px;color:var(--t2);line-height:1.6;margin-bottom:10px}.arc-details{display:flex;gap:16px;font-size:12px;color:var(--t3);margin-bottom:10px}.arc-card details{margin-top:8px;font-size:12px;color:var(--t3)}.arc-card details summary{cursor:pointer;color:var(--t4);margin-bottom:4px}.arc-card details ul{padding-left:16px}.arc-card details li{font-size:11px;line-height:1.7}
.error{color:#ef4444;font-size:12px;margin-top:8px}
.wizard{max-width:540px;margin:40px auto;padding:24px;display:flex;flex-direction:column;gap:20px}
.wizard header{display:flex;justify-content:space-between;align-items:center}
.steps{display:flex;gap:8px;justify-content:center}.steps span{width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;background:var(--border);color:var(--t4)}.steps span.active{background:var(--accent);color:#fff}
.goal-card{border:1px solid var(--border);border-radius:8px;padding:16px;text-align:left;display:flex;flex-direction:column;gap:6px;transition:all .12s}.goal-card.selected,.goal-card:hover{border-color:var(--accent);background:rgba(113,112,255,0.06)}.goal-card strong{font-size:15px;color:var(--t1)}.goal-card small{font-size:12px;color:var(--t3)}
.wizard label{display:flex;flex-direction:column;gap:6px;font-size:12px;color:var(--t3)}.wizard input,.wizard select,.wizard textarea{background:var(--bg-surface);border:1px solid var(--border);border-radius:6px;padding:8px 12px;color:var(--t1);font-size:13px;font-family:inherit}.wizard textarea{resize:vertical;min-height:80px}.wizard select{appearance:auto}.wizard input[type=number]{width:100px}
.wizard footer{display:flex;justify-content:space-between;align-items:center}
.confirm{display:flex;flex-wrap:wrap;gap:12px}.confirm div{flex:1;min-width:120px;background:var(--bg-surface);border:1px solid var(--border);border-radius:6px;padding:12px}.confirm small{font-size:10px;color:var(--t4);display:block;margin-bottom:4px}.confirm strong{font-size:13px;color:var(--t1)}
.hint{font-size:11px;color:var(--t4)}

.workspace-layout{display:grid;grid-template-columns:220px 1fr 240px;height:calc(100vh - 44px);overflow:hidden}
.catalog-panel{background:var(--bg-surface);border-right:1px solid var(--border);overflow-y:auto;padding:12px}
.story-tree{font-size:12px}.story-group{margin-bottom:12px}.story-group strong{display:block;color:var(--t1);font-size:11px;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;padding-left:4px}
.story-unit{display:flex;justify-content:space-between;padding:4px 8px;border-radius:4px;cursor:pointer;color:var(--t3);transition:all .1s}.story-unit:hover{background:rgba(255,255,255,.04);color:var(--t2)}.story-unit.active{background:rgba(113,112,255,.1);color:var(--t1)}.story-unit.adopted .unit-status{color:var(--accent)}.unit-status{font-size:10px;color:var(--t4)}
.center-panel{overflow-y:auto;padding:20px}.center-panel header{padding:0 0 16px;font-size:11px;color:var(--t4)}.center-panel article{max-width:680px}
.candidate-card{background:var(--bg-surface);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:12px}.candidate-card h3{font-size:15px;margin-bottom:8px}.candidate-card p{font-size:12px;color:var(--t3);line-height:1.6;margin-bottom:12px}
.rail-panel{background:var(--bg-surface);border-left:1px solid var(--border);padding:12px;overflow-y:auto;font-size:11px;color:var(--t3)}
.story-section{margin-bottom:24px}.story-section h3{font-size:13px;color:var(--t1);margin-bottom:12px;padding-bottom:6px;border-bottom:1px solid var(--border)}
.entity-cards{display:flex;flex-direction:column;gap:12px}
.entity-card{background:var(--bg-surface);border:1px solid var(--border);border-radius:8px;padding:14px}
.entity-card h4{font-size:14px;margin-bottom:8px}.entity-card h4 small{font-size:10px;color:var(--t4);margin-left:6px}
.entity-card dl{margin:0}.entity-card dt{font-size:10px;color:var(--t4);text-transform:uppercase;margin-top:8px}.entity-card dd{font-size:12px;color:var(--t2);margin:2px 0 8px;white-space:pre-wrap;line-height:1.6}
.thread-item{background:var(--bg-surface);border:1px solid var(--border);border-radius:8px;padding:12px;margin-bottom:8px}.thread-item strong{display:block;font-size:13px;color:var(--t1);margin-bottom:4px}.thread-item .tag{display:inline-block;font-size:10px;padding:2px 6px;border-radius:4px;background:rgba(113,112,255,.15);color:var(--accent)}.thread-item p{font-size:12px;color:var(--t2);margin:6px 0;line-height:1.5}.thread-item small{font-size:10px;color:var(--t4)}
.arc-mini{background:var(--bg-surface);border:1px solid var(--border);border-radius:8px;padding:12px;margin-bottom:8px}.arc-mini strong{font-size:13px;color:var(--t1)}.arc-mini small{font-size:10px;color:var(--t4);margin-left:8px}.arc-mini p{font-size:12px;color:var(--t2);margin:6px 0;line-height:1.5}.emotion{font-size:11px!important;color:var(--accent)!important}
.tag{display:inline-block;font-size:10px;padding:2px 6px;border-radius:4px;background:rgba(255,255,255,.06);color:var(--t4)}

.candidate-actions{display:flex;flex-direction:column;gap:12px;margin-top:16px}
.feedback-row{display:flex;gap:8px;align-items:center}
.feedback-row input{flex:1;background:var(--bg-surface);border:1px solid var(--border);border-radius:6px;padding:8px 12px;color:var(--t1);font-size:12px}
.feedback-row input::placeholder{color:var(--t4);font-size:11px}

.source-controls{display:flex;gap:4px;margin-bottom:8px}
.source-controls button{padding:6px 14px;border-radius:6px;font-size:12px;border:1px solid var(--border);color:var(--t3);background:transparent;transition:all .12s}
.source-controls button.active,.source-controls button:hover{background:var(--accent);color:#fff;border-color:var(--accent)}
.wizard input[type=file]{padding:10px 12px;background:var(--bg-surface);border:1px dashed var(--border);border-radius:6px;cursor:pointer;font-size:12px;color:var(--t3)}
.wizard input[type=file]::file-selector-button{background:var(--accent);color:#fff;border:none;padding:4px 12px;border-radius:4px;cursor:pointer;margin-right:8px;font-size:11px}

.rail-section{margin-bottom:16px}.rail-section h4{font-size:10px;color:var(--t4);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px;padding-bottom:4px;border-bottom:1px solid var(--border)}
.rail-entity{background:rgba(255,255,255,.03);border-radius:6px;padding:8px;margin-bottom:6px}.rail-entity strong{font-size:12px;color:var(--t1);display:block}.rail-entity p{font-size:10px;color:var(--t3);margin-top:4px;line-height:1.4}
.rail-tag{display:inline-block;font-size:9px;padding:1px 5px;border-radius:3px;background:rgba(113,112,255,.1);color:var(--accent)}
.rail-thread{display:flex;align-items:center;gap:6px;padding:4px 0;font-size:11px;color:var(--t2)}.dot{width:6px;height:6px;border-radius:50%;flex-shrink:0}.dot.planted{background:#7170ff}.dot.established{background:#10b981}.dot.overdue{background:#ef4444}
.rail-alert{display:flex;align-items:flex-start;gap:6px;padding:4px 0;font-size:10px;color:var(--t3)}.severity{width:6px;height:6px;border-radius:50%;flex-shrink:0;margin-top:4px}.severity.notice{background:#7170ff}.severity.warning{background:#f59e0b}.severity.risk{background:#ef4444}
.rail-warning{font-size:10px;color:#f59e0b;margin-top:4px}

.agent-chat{display:flex;flex-direction:column;gap:12px}
.chat-msg{background:var(--bg-surface);border:1px solid var(--border);border-radius:8px;overflow:hidden}
.chat-msg.agent{border-left:3px solid var(--accent)}
.chat-msg.user{border-left:3px solid #10b981}
.msg-header{font-size:11px;color:var(--t4);padding:8px 12px 0}
.msg-body{padding:8px 12px}.msg-body pre{white-space:pre-wrap;font-size:13px;line-height:1.7;color:var(--t2);font-family:inherit;margin:0}
.msg-actions{padding:8px 12px;border-top:1px solid var(--border);display:flex;gap:8px}
.chat-input-row{display:flex;gap:8px;margin-top:8px}
.chat-input-row input{flex:1;background:var(--bg-surface);border:1px solid var(--border);border-radius:6px;padding:8px 12px;color:var(--t1);font-size:12px}
.chat-input-row input::placeholder{color:var(--t4);font-size:11px}

</style>