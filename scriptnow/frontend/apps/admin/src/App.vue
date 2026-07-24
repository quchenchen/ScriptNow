<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useLocale, useTheme } from '@scriptnow/shared'
import {
  PhBrain,
  PhBookOpen,
  PhBuildings,
  PhChartLine,
  PhCheckCircle,
  PhCaretRight,
  PhFunnel,
  PhFlowArrow,
  PhGearSix,
  PhMagnifyingGlass,
  PhMoon,
  PhPlus,
  PhPlugsConnected,
  PhPencilSimple,
  PhRobot,
  PhSignOut,
  PhStack,
  PhSun,
  PhTrash,
  PhWarningCircle,
} from '@phosphor-icons/vue'

interface Session { tenant_id: string; user_id: string; is_admin: boolean }
interface Overview { total_tenants: number; active_tenants: number; exhausted_tenants: number; total_tokens: number }
interface Tenant { id: string; name: string; owner_email: string; tier: string; tier_name: string; status: string; monthly_used: number; monthly_quota: number; credits_available: number; created_at: string }
interface Tier { code: string; name: string; rank: number; monthly_price: number; monthly_token_quota: number; enabled: boolean; version: number }
interface UsageSummary { input_tokens: number; output_tokens: number; total_tokens: number; estimated_cost: number; currency: string }
interface UsageRun { run_id: string; trace_id: string; trace_url: string | null; tenant_name: string; project_name: string; status: string; agent_role: string; model_key: string; input_tokens: number; output_tokens: number; estimated_cost: number; currency: string; input_price_per_million: number; output_price_per_million: number; is_mock: boolean; created_at: string }
interface Provider { id: string; key: string; name: string; base_url: string | null; status: string; credential_configured: boolean }
interface DiscoveredModel { key: string; display_name: string }
interface SupplyModel { id: string; key: string; display_name: string; provider_id: string; provider_name: string; provider_status: string; agentscope_class: string; min_tier_code: string; min_tier_name: string; input_price_per_million: number; output_price_per_million: number; enabled: boolean; version: number }
interface ImageModel { id: string; key: string; display_name: string; provider_id: string; provider_name: string; provider_status: string; protocol: 'grsai_image2'; endpoint_path: string; min_tier_code: string; min_tier_name: string; price_per_image: number; default_parameters: Record<string, unknown>; enabled: boolean; version: number }
interface AgentTemplate { id: string; role_key: string; version: number; soul: string; default_model_id: string; published: boolean }
interface ToolGroup { id: string; key: string; name: string; tool_keys: string[]; min_tier_code: string; enabled: boolean; version: number }
interface ToolMount { id: string; role_key: string; tool_group_id: string; enabled: boolean }
interface SkillItem { name: string; description: string; domain: 'platform' | 'novel' | 'script'; references: string[]; digest: string; roles: string[]; stages: string[]; genres: string[]; themes: string[]; styles: string[]; structures: string[]; selection_priority: number; admission_status: string; admission_baseline: string | null; admission_cases: string[] }
interface SkillDetail extends SkillItem { instructions: string }
interface RuntimeSkillPlan { run_id: string; project_id: string; project_name: string; created_at: string; plan: { medium: string; role_key: string; stage: string; resolver_version: number; creative_profile: { genres: string[]; themes: string[]; styles: string[]; structures: string[] }; selections: { key: string; layer: string; score: number; reasons: string[] }[] } }
interface McpServer { id: string; key: string; name: string; transport: 'http' | 'stdio'; public_config: Record<string, unknown>; min_tier_code: string; status: string; latency_ms: number | null; enabled: boolean; confirmation_required: boolean; last_error: string | null }
interface McpTool { id: string; server_id: string; key: string; name: string; description: string; whitelisted: boolean; enabled: boolean }
interface SandboxPolicy { key: string; mode: 'direct' | 'sandbox' | 'sandbox_confirm'; version: number }
interface MemoryEntry { id: string; tenant_id: string; tenant_name: string; project_id: string; project_name: string; role_key: string; content: string; content_hash: string; updated_at: string }
interface MemoryPolicy { role_key: string; memory_max_tokens: number; trigger_ratio: number; reserve_ratio: number; memory_instructions: string; preserve_creative_decisions: boolean; version: number }
interface MemoryAudit { id: string; memory_entry_id: string; operation: string; actor_id: string; created_at: string }

const session = ref<Session | null>(null)
const { isEnglish, locale, t, toggleLocale } = useLocale()
const { resolvedTheme, toggleTheme } = useTheme()
const email = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)
const overview = ref<Overview | null>(null)
const tenants = ref<Tenant[]>([])
const tiers = ref<Tier[]>([])
const activeView = ref<'tenants' | 'usage' | 'supply' | 'capabilities' | 'mcp' | 'memory'>('tenants')
const usageSummary = ref<UsageSummary | null>(null)
const usageRuns = ref<UsageRun[]>([])
const providers = ref<Provider[]>([])
const supplyModels = ref<SupplyModel[]>([])
const imageModels = ref<ImageModel[]>([])
const selectedProviderId = ref('')
const providerSearch = ref('')
const supplySearch = ref('')
const supplyStatus = ref<'all' | 'enabled' | 'disabled'>('all')
const discoveredModels = ref<DiscoveredModel[]>([])
const detectingModels = ref(false)
const agentTemplates = ref<AgentTemplate[]>([])
const toolGroups = ref<ToolGroup[]>([])
const toolMounts = ref<ToolMount[]>([])
const skills = ref<SkillItem[]>([])
const skillsByRole = ref<Record<string, string[]>>({})
const runtimeSkillPlans = ref<RuntimeSkillPlan[]>([])
const selectedRole = ref('director')
const capabilityDomain = ref<'novel' | 'script'>('novel')
const skillDomain = ref<'all' | 'platform' | 'novel' | 'script'>('all')
const skillEditing = ref<SkillDetail | null>(null)
const skillDescription = ref('')
const skillInstructions = ref('')
const mcpServers = ref<McpServer[]>([])
const mcpTools = ref<McpTool[]>([])
const sandboxPolicies = ref<SandboxPolicy[]>([])
const memoryEntries = ref<MemoryEntry[]>([])
const memoryPolicies = ref<MemoryPolicy[]>([])
const memoryAudit = ref<MemoryAudit[]>([])
const mcpOpen = ref(false)
const mcpKey = ref('')
const mcpName = ref('')
const mcpTransport = ref<'http' | 'stdio'>('http')
const mcpEndpoint = ref('')
const mcpSecretName = ref('Authorization')
const mcpSecretValue = ref('')
const mcpTier = ref('plus')
const mcpConfirmationRequired = ref(true)
const memoryEditing = ref<MemoryEntry | null>(null)
const memoryContent = ref('')
const memoryOperation = ref<'correct' | 'compress'>('correct')
const policyEditing = ref<MemoryPolicy | null>(null)
const providerOpen = ref(false)
const providerDeleteTarget = ref<Provider | null>(null)
const providerKey = ref('')
const providerName = ref('')
const providerBaseUrl = ref('')
const providerCredential = ref('')
const modelOpen = ref(false)
const modelKey = ref('')
const modelName = ref('')
const modelProvider = ref('')
const modelClass = ref('OpenAIChatModel')
const modelTier = ref('plus')
const modelInputPrice = ref(0)
const modelOutputPrice = ref(0)
const modelEnabled = ref(true)
const imageModelOpen = ref(false)
const imageModelKey = ref('gpt-image-2')
const imageModelName = ref('GPT Image 2')
const imageModelProvider = ref('')
const imageModelProtocol = ref<'grsai_image2'>('grsai_image2')
const imageModelEndpoint = ref('/v1/api/generate')
const imageModelTier = ref('plus')
const imageModelPrice = ref(0)
const imageModelAspectRatio = ref('1024x1024')
const imageModelReplyType = ref('json')
const imageModelEnabled = ref(true)
const tierConfig = ref<Tier | null>(null)
const tierConfigName = ref('')
const tierConfigRank = ref(0)
const tierConfigPrice = ref(0)
const tierConfigQuota = ref(0)
const tierConfigEnabled = ref(true)
const total = ref(0)
const search = ref('')
const page = ref(0)
const grantTenant = ref<Tenant | null>(null)
const grantTokens = ref(1000)
const grantNote = ref('运营赠送')
const createOpen = ref(false)
const createName = ref('')
const createEmail = ref('')
const createPassword = ref('')
const createTier = ref('plus')
const tierTenant = ref<Tenant | null>(null)
const targetTier = ref('plus')
const tierNote = ref('运营调整等级')
const limit = 50
const pages = computed(() => Math.max(1, Math.ceil(total.value / limit)))
const selectedProvider = computed(() => providers.value.find((item) => item.id === selectedProviderId.value) ?? providers.value[0] ?? null)
const filteredProviders = computed(() => {
  const needle = providerSearch.value.trim().toLocaleLowerCase()
  return providers.value.filter((provider) => !needle || `${provider.name} ${safeProviderKey(provider.key)}`.toLocaleLowerCase().includes(needle))
})
const providerModels = computed(() => supplyModels.value.filter((model) => {
  if (selectedProvider.value && model.provider_id !== selectedProvider.value.id) return false
  if (supplyStatus.value === 'enabled' && !model.enabled) return false
  if (supplyStatus.value === 'disabled' && model.enabled) return false
  const needle = supplySearch.value.trim().toLocaleLowerCase()
  return !needle || `${model.key} ${model.display_name} ${model.agentscope_class}`.toLocaleLowerCase().includes(needle)
}))
const providerImageModels = computed(() => imageModels.value.filter((model) => !selectedProvider.value || model.provider_id === selectedProvider.value.id))
const enabledLanguageModelsFor = (providerId: string) => supplyModels.value.filter((model) => model.provider_id === providerId && model.enabled)
const enabledImageModelsFor = (providerId: string) => imageModels.value.filter((model) => model.provider_id === providerId && model.enabled)
const providerVisualStatus = (provider: Provider) => {
  const languageCount = enabledLanguageModelsFor(provider.id).length
  const imageCount = enabledImageModelsFor(provider.id).length
  if (provider.status === 'connected' && languageCount) return { className: 'connected', label: imageCount ? '语言与生图已配置' : '语言模型在线' }
  if (imageCount && !languageCount) return { className: 'partial', label: '生图已配置 · 未配置语言模型' }
  if (imageCount) return { className: 'partial', label: '生图已配置 · 语言连接失败' }
  if (!provider.credential_configured) return { className: 'unconfigured', label: '未配置凭据' }
  if (provider.status === 'connected') return { className: 'partial', label: 'Provider 已配置 · 尚无模型' }
  return { className: 'error', label: '语言模型连接失败' }
}
const filteredSkills = computed(() => skills.value.filter((skill) => skillDomain.value === 'all' || skill.domain === skillDomain.value))
const skillNamesForRole = (role: string) => (skillsByRole.value[role] ?? []).filter((name) => {
  const skill = skills.value.find((item) => item.name === name)
  return skill?.domain === 'platform' || skill?.domain === capabilityDomain.value
})
const selectedRoleSkillNames = computed(() => new Set(skillNamesForRole(selectedRole.value)))
const viewTitle = computed(() => ({ tenants: t('admin.tenants'), usage: t('admin.usage'), supply: t('admin.supplyManagement'), capabilities: t('admin.capabilities'), mcp: t('admin.mcp'), memory: t('admin.memory') })[activeView.value])
const viewHint = computed(() => (isEnglish.value
  ? ({ tenants: 'Every write is ledgered and audited', usage: 'Usage comes from post-call events and price snapshots', supply: 'Secrets are never revealed · visibility updates immediately', capabilities: 'Roles define duties · Skills define methods · Tools enable action', mcp: 'Deny by default · disconnects degrade safely · external calls require approval', memory: 'Memory content and its audit share one source of truth' })
  : ({ tenants: '所有写操作进入账本与审计', usage: '计量来自模型调用后置事件与价格快照', supply: '密钥不回显 · 可见性即时生效', capabilities: '角色决定职责 · Skill 提供方法 · Tool 提供执行能力', mcp: '默认拒绝 · 断连自动降级 · 外呼需确认', memory: '内容事实源与操作审计同源' }))[activeView.value])
const roleMeta: Record<string, { name: string; responsibility: string }> = {
  director: { name: '创意导演', responsibility: '创意发散、故事核心与方向修订' },
  architect: { name: '架构规划师', responsibility: '蓝图、StoryMap 与叙事结构' },
  writer: { name: '写作者', responsibility: '正文生成、选区改写与格式控制' },
  reviewer: { name: '审读编辑', responsibility: '五维审读、问题定位与修订建议' },
}
const displayedMemoryPolicies = computed(() => memoryPolicies.value.length ? memoryPolicies.value : ['director', 'architect', 'writer', 'reviewer'].map((role_key) => ({ role_key, memory_max_tokens: 4000, trigger_ratio: 0.7, reserve_ratio: 0.2, memory_instructions: '保留创作决策、用户偏好和项目禁用词。', preserve_creative_decisions: true, version: 0 })))
const formatNumber = (value: number) => new Intl.NumberFormat(locale.value).format(value)
const formatDate = (value: string) => new Intl.DateTimeFormat(locale.value, {
  dateStyle: 'medium',
  timeStyle: 'short',
}).format(new Date(value))
const safeProviderKey = (value: string) => /^sk[-_]/i.test(value) ? '已配置 Provider' : value
const csrf = () => document.cookie.split('; ').find((item) => item.startsWith('sf_csrf='))?.split('=')[1] ?? ''

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body) headers.set('Content-Type', 'application/json')
  if ((init.method ?? 'GET') !== 'GET') headers.set('X-CSRF-Token', decodeURIComponent(csrf()))
  const response = await fetch(`/api${path}`, { ...init, headers, credentials: 'include' })
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(response.status === 403 ? '当前账户没有管理员权限。' : payload?.detail ?? '请求失败')
  }
  return response.status === 204 ? undefined as T : response.json()
}
async function load() {
  busy.value = true
  error.value = ''
  try {
    const [summary, result, tierResult, usageResult, supplyResult, capabilityResult, skillResult, mcpResult, memoryResult] = await Promise.all([
      request<Overview>('/admin/api/overview'),
      request<{ items: Tenant[]; total: number }>(`/admin/api/tenants?search=${encodeURIComponent(search.value)}&limit=${limit}&offset=${page.value * limit}`),
      request<Tier[]>('/admin/api/tiers'),
      request<{ summary: UsageSummary; items: UsageRun[] }>('/admin/api/usage/runs?limit=25&offset=0'),
      request<{ providers: Provider[]; models: SupplyModel[]; image_models: ImageModel[]; tiers: Tier[] }>('/admin/api/supply'),
      request<{ templates: AgentTemplate[]; tool_groups: ToolGroup[]; mounts: ToolMount[]; skill_plans: RuntimeSkillPlan[] }>('/admin/api/capabilities'),
      request<{ skills: SkillItem[]; mounted_by_role: Record<string, string[]> }>('/admin/api/skills'),
      request<{ servers: McpServer[]; tools: McpTool[]; policies: SandboxPolicy[] }>('/admin/api/mcp-governance'),
      request<{ items: MemoryEntry[]; policies: MemoryPolicy[]; audit: MemoryAudit[] }>('/admin/api/memories'),
    ])
    overview.value = summary
    tenants.value = result.items
    total.value = result.total
    tiers.value = tierResult
    usageSummary.value = usageResult.summary
    usageRuns.value = usageResult.items
    providers.value = supplyResult.providers
    if (!selectedProviderId.value || !supplyResult.providers.some((item) => item.id === selectedProviderId.value)) selectedProviderId.value = supplyResult.providers[0]?.id ?? ''
    supplyModels.value = supplyResult.models
    imageModels.value = supplyResult.image_models ?? []
    agentTemplates.value = capabilityResult.templates
    toolGroups.value = capabilityResult.tool_groups
    toolMounts.value = capabilityResult.mounts
    runtimeSkillPlans.value = (capabilityResult.skill_plans ?? []).map((item) => ({
      ...item,
      plan: {
        ...item.plan,
        creative_profile: item.plan.creative_profile ?? { genres: [], themes: [], styles: [], structures: [] },
        selections: item.plan.selections ?? [],
      },
    }))
    skills.value = skillResult.skills.map((skill) => ({
      ...skill,
      roles: skill.roles ?? [],
      stages: skill.stages ?? [],
      genres: skill.genres ?? [],
      themes: skill.themes ?? [],
      styles: skill.styles ?? [],
      structures: skill.structures ?? [],
      selection_priority: skill.selection_priority ?? 0,
      admission_status: skill.admission_status ?? 'legacy',
      admission_baseline: skill.admission_baseline ?? null,
      admission_cases: skill.admission_cases ?? [],
    }))
    skillsByRole.value = skillResult.mounted_by_role
    mcpServers.value = mcpResult.servers
    mcpTools.value = mcpResult.tools
    sandboxPolicies.value = mcpResult.policies
    memoryEntries.value = memoryResult.items
    memoryPolicies.value = memoryResult.policies
    memoryAudit.value = memoryResult.audit
  } catch (caught) { error.value = caught instanceof Error ? caught.message : '请求失败' }
  finally { busy.value = false }
}
async function login() {
  busy.value = true
  error.value = ''
  try {
    session.value = await request<Session>('/auth/login', { method: 'POST', body: JSON.stringify({ email: email.value, password: password.value }) })
    if (!session.value.is_admin) throw new Error('当前账户没有管理员权限。')
    await load()
  } catch (caught) { session.value = null; error.value = caught instanceof Error ? caught.message : '登录失败' }
  finally { busy.value = false }
}
async function logout() {
  await request('/auth/logout', { method: 'POST' })
  session.value = null
}
async function restore() {
  try {
    const current = await request<Session>('/auth/me')
    if (current.is_admin) { session.value = current; await load() }
  } catch { session.value = null }
}
function submitSearch() { page.value = 0; void load() }
async function submitGrant() {
  if (!grantTenant.value) return
  busy.value = true
  error.value = ''
  try {
    await request(`/admin/api/tenants/${grantTenant.value.id}/grants`, {
      method: 'POST',
      body: JSON.stringify({ tier: grantTenant.value.tier, tokens: grantTokens.value, note: grantNote.value, idempotency_key: crypto.randomUUID() }),
    })
    grantTenant.value = null
    await load()
  } catch (caught) { error.value = caught instanceof Error ? caught.message : '赠点失败' }
  finally { busy.value = false }
}
async function submitCreate() {
  busy.value = true
  error.value = ''
  try {
    await request('/admin/api/tenants', {
      method: 'POST',
      body: JSON.stringify({ name: createName.value, owner_email: createEmail.value, temporary_password: createPassword.value, tier: createTier.value }),
    })
    createOpen.value = false
    createName.value = ''
    createEmail.value = ''
    createPassword.value = ''
    await load()
  } catch (caught) { error.value = caught instanceof Error ? caught.message : '租户创建失败' }
  finally { busy.value = false }
}
function openTier(tenant: Tenant) {
  tierTenant.value = tenant
  targetTier.value = tenant.tier
}
async function submitTier() {
  if (!tierTenant.value) return
  busy.value = true
  error.value = ''
  try {
    await request(`/admin/api/tenants/${tierTenant.value.id}/tier`, {
      method: 'PATCH',
      body: JSON.stringify({ tier: targetTier.value, note: tierNote.value }),
    })
    tierTenant.value = null
    await load()
  } catch (caught) { error.value = caught instanceof Error ? caught.message : '等级调整失败' }
  finally { busy.value = false }
}
async function toggleStatus(tenant: Tenant) {
  busy.value = true
  error.value = ''
  try {
    await request(`/admin/api/tenants/${tenant.id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status: tenant.status === 'active' ? 'suspended' : 'active' }),
    })
    await load()
  } catch (caught) { error.value = caught instanceof Error ? caught.message : '状态更新失败' }
  finally { busy.value = false }
}
function resetProviderForm(provider?: Provider) {
  providerKey.value = provider?.key ?? ''
  providerName.value = provider?.name ?? ''
  providerBaseUrl.value = provider?.base_url ?? ''
  providerCredential.value = ''
  providerOpen.value = true
}
function selectProvider(provider: Provider) {
  selectedProviderId.value = provider.id
  discoveredModels.value = []
  supplySearch.value = ''
  supplyStatus.value = 'all'
}
async function submitProvider() {
  busy.value = true; error.value = ''
  try {
    const provider = await request<Provider>('/admin/api/providers', { method: 'POST', body: JSON.stringify({ key: providerKey.value, name: providerName.value, base_url: providerBaseUrl.value || null, credential: providerCredential.value }) })
    providerOpen.value = false; selectedProviderId.value = provider.id; await load()
  } catch (caught) { error.value = caught instanceof Error ? caught.message : 'Provider 保存失败' }
  finally { busy.value = false }
}
async function deleteProvider() {
  if (!providerDeleteTarget.value) return
  busy.value = true; error.value = ''
  try {
    await request(`/admin/api/providers/${providerDeleteTarget.value.id}`, { method: 'DELETE' })
    providerDeleteTarget.value = null
    selectedProviderId.value = ''
    discoveredModels.value = []
    await load()
  } catch (caught) { error.value = caught instanceof Error ? caught.message : 'Provider 删除失败' }
  finally { busy.value = false }
}
async function openSkillEditor(skill: SkillItem) {
  busy.value = true; error.value = ''
  try {
    const detail = await request<SkillDetail>(`/admin/api/skills/${encodeURIComponent(skill.name)}`)
    skillEditing.value = detail
    skillDescription.value = detail.description
    skillInstructions.value = detail.instructions
  } catch (caught) { error.value = caught instanceof Error ? caught.message : 'Skill 读取失败' }
  finally { busy.value = false }
}
async function submitSkill() {
  if (!skillEditing.value) return
  busy.value = true; error.value = ''
  try {
    await request(`/admin/api/skills/${encodeURIComponent(skillEditing.value.name)}`, {
      method: 'PUT',
      body: JSON.stringify({ description: skillDescription.value, instructions: skillInstructions.value, expected_digest: skillEditing.value.digest }),
    })
    skillEditing.value = null
    await load()
  } catch (caught) { error.value = caught instanceof Error ? caught.message : 'Skill 保存失败' }
  finally { busy.value = false }
}
async function discoverModels(provider = selectedProvider.value) {
  if (!provider) return
  detectingModels.value = true; error.value = ''; discoveredModels.value = []
  try {
    discoveredModels.value = await request<DiscoveredModel[]>(`/admin/api/providers/${provider.id}/discover-models`, { method: 'POST' })
    await load()
  } catch (caught) { error.value = caught instanceof Error ? `模型检测失败：${caught.message}` : '模型检测失败' }
  finally { detectingModels.value = false }
}
function importDiscoveredModel(model: DiscoveredModel) {
  openModel()
  modelKey.value = model.key
  modelName.value = model.display_name
  modelEnabled.value = false
}
async function submitModel() {
  busy.value = true; error.value = ''
  try {
    await request('/admin/api/models', { method: 'POST', body: JSON.stringify({ key: modelKey.value, display_name: modelName.value, provider_id: modelProvider.value, agentscope_class: modelClass.value, min_tier_code: modelTier.value, input_price_per_million: modelInputPrice.value, output_price_per_million: modelOutputPrice.value, enabled: modelEnabled.value }) })
    modelOpen.value = false; await load()
  } catch (caught) { error.value = caught instanceof Error ? caught.message : '模型保存失败' }
  finally { busy.value = false }
}
function openImageModel(model?: ImageModel) {
  imageModelKey.value = model?.key ?? 'gpt-image-2'
  imageModelName.value = model?.display_name ?? 'GPT Image 2'
  imageModelProvider.value = model?.provider_id ?? selectedProvider.value?.id ?? providers.value[0]?.id ?? ''
  imageModelProtocol.value = model?.protocol ?? 'grsai_image2'
  imageModelEndpoint.value = model?.endpoint_path ?? '/v1/api/generate'
  imageModelTier.value = model?.min_tier_code ?? tiers.value[0]?.code ?? 'plus'
  imageModelPrice.value = model?.price_per_image ?? 0
  imageModelAspectRatio.value = String(model?.default_parameters.aspectRatio ?? '1024x1024')
  imageModelReplyType.value = String(model?.default_parameters.replyType ?? 'json')
  imageModelEnabled.value = model?.enabled ?? true
  imageModelOpen.value = true
}
async function submitImageModel() {
  busy.value = true; error.value = ''
  try {
    await request('/admin/api/image-models', { method: 'POST', body: JSON.stringify({
      key: imageModelKey.value, display_name: imageModelName.value, provider_id: imageModelProvider.value,
      protocol: imageModelProtocol.value, endpoint_path: imageModelEndpoint.value,
      min_tier_code: imageModelTier.value, price_per_image: imageModelPrice.value,
      default_parameters: { aspectRatio: imageModelAspectRatio.value, replyType: imageModelReplyType.value },
      enabled: imageModelEnabled.value,
    }) })
    imageModelOpen.value = false; await load()
  } catch (caught) { error.value = caught instanceof Error ? caught.message : '生图模型保存失败' }
  finally { busy.value = false }
}
function openModel(model?: SupplyModel) {
  modelKey.value = model?.key ?? ''
  modelName.value = model?.display_name ?? ''
  modelProvider.value = model?.provider_id ?? selectedProvider.value?.id ?? providers.value[0]?.id ?? ''
  modelClass.value = model?.agentscope_class ?? 'OpenAIChatModel'
  modelTier.value = model?.min_tier_code ?? tiers.value[0]?.code ?? 'plus'
  modelInputPrice.value = model?.input_price_per_million ?? 0
  modelOutputPrice.value = model?.output_price_per_million ?? 0
  modelEnabled.value = model?.enabled ?? true
  modelOpen.value = true
}
function openTierConfig(tier: Tier) {
  tierConfig.value = tier; tierConfigName.value = tier.name; tierConfigRank.value = tier.rank; tierConfigQuota.value = tier.monthly_token_quota; tierConfigPrice.value = tier.monthly_price; tierConfigEnabled.value = tier.enabled
}
async function submitTierConfig() {
  if (!tierConfig.value) return
  busy.value = true; error.value = ''
  try {
    await request(`/admin/api/tiers/${tierConfig.value.code}`, { method: 'PUT', body: JSON.stringify({ name: tierConfigName.value, rank: tierConfigRank.value, monthly_price: tierConfigPrice.value, monthly_token_quota: tierConfigQuota.value, enabled: tierConfigEnabled.value }) })
    tierConfig.value = null; await load()
  } catch (caught) { error.value = caught instanceof Error ? caught.message : 'Tier 保存失败' }
  finally { busy.value = false }
}
async function publishTemplate(template: AgentTemplate) {
  busy.value = true; error.value = ''
  try { await request(`/admin/api/agent-templates/${template.id}/publish`, { method: 'POST' }); await load() }
  catch (caught) { error.value = caught instanceof Error ? caught.message : '模板发布失败' }
  finally { busy.value = false }
}
async function toggleMount(roleKey: string, group: ToolGroup) {
  const current = toolMounts.value.find((item) => item.role_key === roleKey && item.tool_group_id === group.id)
  busy.value = true; error.value = ''
  try { await request('/admin/api/tool-mounts', { method: 'PUT', body: JSON.stringify({ role_key: roleKey, tool_group_id: group.id, enabled: !current?.enabled }) }); await load() }
  catch (caught) { error.value = caught instanceof Error ? caught.message : '挂载更新失败' }
  finally { busy.value = false }
}
function mountEnabled(roleKey: string, groupId: string) { return toolMounts.value.some((item) => item.role_key === roleKey && item.tool_group_id === groupId && item.enabled) }
async function submitMcp() {
  busy.value = true; error.value = ''
  const config = mcpTransport.value === 'http'
    ? { url: mcpEndpoint.value, headers: mcpSecretValue.value ? { [mcpSecretName.value]: mcpSecretValue.value } : {} }
    : { command: mcpEndpoint.value, args: [], env: mcpSecretValue.value ? { [mcpSecretName.value]: mcpSecretValue.value } : {} }
  try {
    await request('/admin/api/mcp-servers', { method: 'POST', body: JSON.stringify({ key: mcpKey.value, name: mcpName.value, transport: mcpTransport.value, config, min_tier_code: mcpTier.value, enabled: true, confirmation_required: mcpConfirmationRequired.value }) })
    mcpOpen.value = false; mcpSecretValue.value = ''; await load()
  } catch (caught) { error.value = caught instanceof Error ? caught.message : 'MCP 保存失败' }
  finally { busy.value = false }
}
async function discoverMcp(server: McpServer) {
  busy.value = true; error.value = ''
  try { await request(`/admin/api/mcp-servers/${server.id}/discover`, { method: 'POST' }); await load() }
  catch (caught) { error.value = caught instanceof Error ? caught.message : 'MCP 连接或发现失败' }
  finally { busy.value = false }
}
async function toggleWhitelist(tool: McpTool) {
  busy.value = true; error.value = ''
  try { await request(`/admin/api/mcp-tools/${tool.id}/whitelist`, { method: 'PUT', body: JSON.stringify({ whitelisted: !tool.whitelisted }) }); await load() }
  catch (caught) { error.value = caught instanceof Error ? caught.message : '白名单更新失败' }
  finally { busy.value = false }
}
async function packageMcpTool(tool: McpTool) {
  const server = mcpServers.value.find((item) => item.id === tool.server_id)
  if (!server || !tool.whitelisted || server.confirmation_required) return
  busy.value = true; error.value = ''
  try {
    const safeKey = `mcp-${server.key}-${tool.key}`.toLowerCase().replace(/[^a-z0-9_.-]+/g, '-')
    const group = await request<{ id: string }>('/admin/api/tool-groups', {
      method: 'POST',
      body: JSON.stringify({
        key: safeKey,
        name: `${server.name} · ${tool.name}`,
        tool_keys: [`mcp.${server.key}.${tool.key}`],
        min_tier_code: server.min_tier_code,
        enabled: true,
      }),
    })
    await request('/admin/api/tool-mounts', {
      method: 'PUT',
      body: JSON.stringify({ role_key: selectedRole.value, tool_group_id: group.id, enabled: true }),
    })
    await load()
  } catch (caught) { error.value = caught instanceof Error ? caught.message : 'MCP 工具挂载失败' }
  finally { busy.value = false }
}
async function setSandbox(mode: SandboxPolicy['mode']) {
  busy.value = true; error.value = ''
  try { await request('/admin/api/sandbox-policies/default', { method: 'PUT', body: JSON.stringify({ mode }) }); await load() }
  catch (caught) { error.value = caught instanceof Error ? caught.message : '沙箱策略更新失败' }
  finally { busy.value = false }
}
function editMemory(entry: MemoryEntry, operation: 'correct' | 'compress') { memoryEditing.value = entry; memoryContent.value = entry.content; memoryOperation.value = operation }
async function submitMemory() {
  if (!memoryEditing.value) return
  const item = memoryEditing.value
  const suffix = memoryOperation.value === 'compress' ? '/compress' : ''
  busy.value = true; error.value = ''
  try { await request(`/admin/api/memories/${item.id}${suffix}?tenant_id=${item.tenant_id}&project_id=${item.project_id}`, { method: memoryOperation.value === 'compress' ? 'POST' : 'PUT', body: JSON.stringify({ content: memoryContent.value }) }); memoryEditing.value = null; await load() }
  catch (caught) { error.value = caught instanceof Error ? caught.message : '记忆更新失败' }
  finally { busy.value = false }
}
async function deleteMemory(entry: MemoryEntry) {
  busy.value = true; error.value = ''
  try { await request(`/admin/api/memories/${entry.id}?tenant_id=${entry.tenant_id}&project_id=${entry.project_id}`, { method: 'DELETE' }); await load() }
  catch (caught) { error.value = caught instanceof Error ? caught.message : '记忆删除失败' }
  finally { busy.value = false }
}
async function submitMemoryPolicy() {
  if (!policyEditing.value) return
  busy.value = true; error.value = ''
  try { await request(`/admin/api/memory-policies/${policyEditing.value.role_key}`, { method: 'PUT', body: JSON.stringify({ memory_max_tokens: policyEditing.value.memory_max_tokens, trigger_ratio: policyEditing.value.trigger_ratio, reserve_ratio: policyEditing.value.reserve_ratio, memory_instructions: policyEditing.value.memory_instructions, preserve_creative_decisions: true }) }); policyEditing.value = null; await load() }
  catch (caught) { error.value = caught instanceof Error ? caught.message : '记忆策略更新失败' }
  finally { busy.value = false }
}
onMounted(() => void restore())
</script>

<template>
  <main v-if="!session" v-ui-locale="locale" class="admin-login">
    <section><span>S</span><p class="eyebrow">ScriptNow Admin</p><h1>{{ t('admin.hero') }}</h1><p>{{ t('admin.heroDescription') }}</p></section>
    <form @submit.prevent="login"><div class="admin-interface-controls"><button class="admin-theme-switch" type="button" :aria-label="resolvedTheme === 'dark' ? t('theme.light') : t('theme.dark')" @click="toggleTheme"><PhSun v-if="resolvedTheme === 'dark'" /><PhMoon v-else /></button><button class="admin-locale-switch" type="button" :aria-label="t('locale.label')" @click="toggleLocale">{{ t('locale.action') }}</button></div><p class="eyebrow">{{ t('admin.loginEyebrow') }}</p><h2>{{ t('admin.loginTitle') }}</h2><label>{{ t('common.email') }}<input v-model="email" type="email" required /></label><label>{{ t('common.password') }}<input v-model="password" type="password" minlength="12" required /></label><p v-if="error" class="error">{{ error }}</p><button :disabled="busy">{{ busy ? t('admin.loggingIn') : t('admin.login') }}</button></form>
  </main>
  <div v-else v-ui-locale="locale" class="admin-shell">
    <aside><a href="/" class="admin-brand"><b>S</b><span>ScriptNow<small>Admin Console</small></span></a><nav><p>{{ t('admin.operations') }}</p><button :class="{ active: activeView === 'tenants' }" @click="activeView = 'tenants'"><PhBuildings />{{ t('admin.tenants') }}</button><button :class="{ active: activeView === 'usage' }" @click="activeView = 'usage'"><PhChartLine />{{ t('admin.usage') }}</button><p>{{ t('admin.supply') }}</p><button :class="{ active: activeView === 'supply' }" @click="activeView = 'supply'"><PhStack />Provider / Model</button><button :class="{ active: activeView === 'capabilities' }" @click="activeView = 'capabilities'"><PhRobot />{{ t('admin.capabilities') }}</button><button :class="{ active: activeView === 'mcp' }" @click="activeView = 'mcp'"><PhPlugsConnected />{{ t('admin.mcp') }}</button><button :class="{ active: activeView === 'memory' }" @click="activeView = 'memory'"><PhBrain />{{ t('admin.memory') }}</button></nav><button class="admin-logout" @click="logout"><PhSignOut />{{ t('admin.logout') }}</button></aside>
    <section class="admin-content">
      <header><div><p class="eyebrow">Platform Operations</p><h1>{{ viewTitle }}</h1></div><div class="admin-header-actions"><span>{{ viewHint }}</span><div class="admin-interface-controls"><button class="admin-theme-switch" type="button" :aria-label="resolvedTheme === 'dark' ? t('theme.light') : t('theme.dark')" @click="toggleTheme"><PhSun v-if="resolvedTheme === 'dark'" /><PhMoon v-else /></button><button class="admin-locale-switch" type="button" :aria-label="t('locale.label')" @click="toggleLocale">{{ t('locale.action') }}</button></div></div></header>
      <p v-if="error" class="error">{{ error }}</p>
      <template v-if="activeView === 'tenants'"><div v-if="overview" class="kpi-grid"><article><small>租户总数</small><strong>{{ overview.total_tenants }}</strong></article><article><small>正常租户</small><strong>{{ overview.active_tenants }}</strong></article><article :class="{ warning: overview.exhausted_tenants }"><small>额度耗尽</small><strong>{{ overview.exhausted_tenants }}</strong></article><article><small>累计 Tokens</small><strong>{{ formatNumber(overview.total_tokens) }}</strong></article></div>
      <section class="tenant-panel"><header><div><h2>租户列表</h2><small>真实分页与名称/邮箱搜索</small></div><div class="tenant-tools"><button class="create-tenant" @click="createOpen = true">＋ 创建租户</button><form @submit.prevent="submitSearch"><input v-model="search" placeholder="搜索租户或邮箱" /><button>搜索</button></form></div></header><div class="table-wrap"><table><thead><tr><th>租户</th><th>等级</th><th>状态</th><th>本月用量</th><th>点数</th><th>加入时间</th><th>操作</th></tr></thead><tbody><tr v-for="tenant in tenants" :key="tenant.id"><td><strong>{{ tenant.name }}</strong><small>{{ tenant.owner_email }}</small></td><td><span class="tier-chip">{{ tenant.tier_name }}</span></td><td><span :class="`status-${tenant.status}`">{{ tenant.status === 'active' ? '正常' : '停用' }}</span></td><td><div class="usage-line"><i :style="{ width: `${Math.min(100, tenant.monthly_quota ? tenant.monthly_used / tenant.monthly_quota * 100 : 0)}%` }" /></div><small>{{ formatNumber(tenant.monthly_used) }} / {{ formatNumber(tenant.monthly_quota) }}</small></td><td>{{ formatNumber(tenant.credits_available) }}</td><td>{{ formatDate(tenant.created_at) }}</td><td><div class="row-actions"><button @click="grantTenant = tenant">赠点</button><button @click="openTier(tenant)">改级</button><button :disabled="tenant.id === session?.tenant_id" @click="toggleStatus(tenant)">{{ tenant.status === 'active' ? '停用' : '恢复' }}</button></div></td></tr></tbody></table></div><footer><span>共 {{ total }} 个租户</span><div><button :disabled="page === 0" @click="page--; load()">上一页</button><span>{{ page + 1 }} / {{ pages }}</span><button :disabled="page + 1 >= pages" @click="page++; load()">下一页</button></div></footer></section></template>
      <template v-else-if="activeView === 'usage'"><div v-if="usageSummary" class="kpi-grid"><article><small>输入 Tokens</small><strong>{{ formatNumber(usageSummary.input_tokens) }}</strong></article><article><small>输出 Tokens</small><strong>{{ formatNumber(usageSummary.output_tokens) }}</strong></article><article><small>总 Tokens</small><strong>{{ formatNumber(usageSummary.total_tokens) }}</strong></article><article><small>估算成本</small><strong>¥{{ usageSummary.estimated_cost.toFixed(4) }}</strong></article></div><section class="tenant-panel usage-panel"><header><div><h2>最近运行</h2><small>价格按每次模型调用时快照，不使用当前价回算</small></div></header><div class="table-wrap"><table><thead><tr><th>租户 / 项目</th><th>Agent / 模型</th><th>Tokens</th><th>价格快照</th><th>成本</th><th>Trace</th><th>时间</th></tr></thead><tbody><tr v-for="run in usageRuns" :key="run.run_id"><td><strong>{{ run.tenant_name }}</strong><small>{{ run.project_name }}</small></td><td><strong>{{ run.agent_role }}</strong><small>{{ run.model_key }} <span v-if="run.is_mock" class="mock-chip">Mock</span></small></td><td>{{ formatNumber(run.input_tokens + run.output_tokens) }}<small>入 {{ formatNumber(run.input_tokens) }} / 出 {{ formatNumber(run.output_tokens) }}</small></td><td>¥{{ run.input_price_per_million }} / ¥{{ run.output_price_per_million }}<small>每百万入 / 出</small></td><td>¥{{ run.estimated_cost.toFixed(6) }}</td><td><a v-if="run.trace_url" :href="run.trace_url" target="_blank" rel="noreferrer">打开 Studio</a><span v-else :title="run.trace_id">未配置 Studio</span></td><td>{{ formatDate(run.created_at) }}</td></tr></tbody></table></div></section></template>
      <template v-else-if="activeView === 'supply'">
        <section class="supply-workspace">
          <aside class="provider-rail">
            <header><div><p class="eyebrow">Provider</p><h2>连接目录</h2></div><button class="icon-button" aria-label="新增 Provider" @click="resetProviderForm()"><PhPlus /></button></header>
            <label class="provider-search"><PhMagnifyingGlass /><input v-model="providerSearch" placeholder="搜索 Provider" /></label>
            <div class="provider-list">
              <button v-for="provider in filteredProviders" :key="provider.id" :class="{ selected: selectedProvider?.id === provider.id }" @click="selectProvider(provider)">
                <i :class="providerVisualStatus(provider).className" />
                <span><strong>{{ provider.name }}</strong><small>{{ safeProviderKey(provider.key) }} · {{ providerVisualStatus(provider).label }}</small></span>
                <PhCaretRight />
              </button>
              <p v-if="!providers.length" class="empty-state">尚未配置 Provider</p>
            </div>
          </aside>
          <main class="model-catalog">
            <header v-if="selectedProvider" class="provider-summary">
              <div class="provider-identity"><span class="provider-mark">{{ selectedProvider.name.slice(0, 1) }}</span><div><div><h2>{{ selectedProvider.name }}</h2><span :class="`status-${providerVisualStatus(selectedProvider).className}`">{{ providerVisualStatus(selectedProvider).label }}</span></div><p>{{ safeProviderKey(selectedProvider.key) }} · {{ selectedProvider.base_url || '使用 Provider 默认端点' }}</p></div></div>
              <div class="provider-actions"><button :disabled="detectingModels" @click="discoverModels()"><PhMagnifyingGlass />{{ detectingModels ? '检测中…' : '检测语言模型' }}</button><button @click="resetProviderForm(selectedProvider)"><PhGearSix />配置 Provider</button><button class="danger-action" @click="providerDeleteTarget = selectedProvider"><PhTrash />删除</button><button @click="openModel()"><PhPlus />语言模型</button><button class="primary" @click="openImageModel()"><PhPlus />生图模型</button></div>
              <dl><div><dt>凭据</dt><dd>{{ selectedProvider.credential_configured ? '已安全配置（未回显）' : '未配置' }}</dd></div><div><dt>语言模型</dt><dd><PhCheckCircle v-if="selectedProvider.status === 'connected' && enabledLanguageModelsFor(selectedProvider.id).length" /><PhWarningCircle v-else />{{ enabledLanguageModelsFor(selectedProvider.id).length ? (selectedProvider.status === 'connected' ? `${enabledLanguageModelsFor(selectedProvider.id).length} 个已连接` : '连接检测失败') : '未配置' }}</dd></div><div><dt>生图模型</dt><dd><PhCheckCircle v-if="enabledImageModelsFor(selectedProvider.id).length" /><PhWarningCircle v-else />{{ enabledImageModelsFor(selectedProvider.id).length ? `${enabledImageModelsFor(selectedProvider.id).length} 个已配置，调用时验证` : '未配置' }}</dd></div></dl>
            </header>
            <div v-if="selectedProvider" class="catalog-body">
              <section v-if="discoveredModels.length" class="discovery-results"><header><div><strong>检测到 {{ discoveredModels.length }} 个模型</strong><small>选择模型后补充价格与等级；默认保持停用，确认后再开放给 Creator。</small></div><button aria-label="关闭检测结果" @click="discoveredModels = []">×</button></header><div><button v-for="model in discoveredModels" :key="model.key" @click="importDiscoveredModel(model)"><span>{{ model.display_name }}</span><small>导入配置</small></button></div></section>
              <header><div><p class="eyebrow">Language Models</p><h2>语言模型</h2></div><div class="catalog-tools"><label><PhMagnifyingGlass /><input v-model="supplySearch" placeholder="搜索模型、Key 或 Class" /></label><label><PhFunnel /><select v-model="supplyStatus"><option value="all">全部状态</option><option value="enabled">已启用</option><option value="disabled">已停用</option></select></label></div></header>
              <div class="table-wrap model-table"><table><thead><tr><th>模型</th><th>AgentScope Class</th><th>输入价 / 百万</th><th>输出价 / 百万</th><th>最低等级</th><th>版本</th><th>状态</th><th><span class="sr-only">操作</span></th></tr></thead><tbody><tr v-for="model in providerModels" :key="model.id"><td><strong>{{ model.display_name }}</strong><small>{{ model.key }}</small></td><td>{{ model.agentscope_class }}</td><td>¥{{ model.input_price_per_million }}</td><td>¥{{ model.output_price_per_million }}</td><td><span class="tier-chip">{{ model.min_tier_name }}</span></td><td>v{{ model.version }}</td><td><span :class="model.enabled ? 'status-connected' : 'status-suspended'">{{ model.enabled ? '启用' : '停用' }}</span></td><td><button class="table-action" @click="openModel(model)">配置</button></td></tr></tbody></table><p v-if="!providerModels.length" class="empty-state">此 Provider 下没有符合条件的模型。</p></div>
              <header><div><p class="eyebrow">Image Models</p><h2>生图模型</h2><small>封面 Prompt 由包装 Agent 根据作品事实生成，模型只负责图像执行。</small></div><button class="primary" @click="openImageModel()"><PhPlus />新增生图模型</button></header>
              <div class="table-wrap model-table"><table><thead><tr><th>模型</th><th>代理协议</th><th>生成端点</th><th>默认比例</th><th>单图价格</th><th>最低等级</th><th>状态</th><th><span class="sr-only">操作</span></th></tr></thead><tbody><tr v-for="model in providerImageModels" :key="model.id"><td><strong>{{ model.display_name }}</strong><small>{{ model.key }}</small></td><td>{{ model.protocol === 'grsai_image2' ? 'Grsai Image2' : 'OpenAI Images' }}</td><td>{{ model.endpoint_path }}</td><td>{{ model.default_parameters.aspectRatio ?? 'auto' }}</td><td>¥{{ model.price_per_image }}</td><td><span class="tier-chip">{{ model.min_tier_name }}</span></td><td><span :class="model.enabled ? 'status-connected' : 'status-suspended'">{{ model.enabled ? '启用' : '停用' }}</span></td><td><button class="table-action" @click="openImageModel(model)">配置</button></td></tr></tbody></table><p v-if="!providerImageModels.length" class="empty-state">此 Provider 尚未配置生图模型。</p></div>
            </div>
            <div v-else class="supply-empty"><PhStack /><h2>开始配置模型供给</h2><p>先创建并连接一个 Provider，再登记可供 Creator 使用的模型。</p><button class="primary" @click="resetProviderForm()">新增 Provider</button></div>
          </main>
        </section>
      </template>
      <template v-else-if="activeView === 'capabilities'">
        <section class="capability-flow" aria-label="Agent 能力组成"><span><PhRobot />Agent 角色</span><PhFlowArrow /><span><PhBookOpen />Skills 方法</span><PhFlowArrow /><span><PhStack />Tools 执行</span><PhFlowArrow /><span><PhPlugsConnected />MCP 外部能力</span></section>
        <section class="agent-capability-layout">
          <aside class="agent-role-panel"><header><p class="eyebrow">Agent Team</p><h2>选择角色</h2><small>查看这个 Agent 在指定产品领域的真实运行时能力。</small><div class="domain-switch"><button :class="{ active: capabilityDomain === 'novel' }" @click="capabilityDomain = 'novel'">小说</button><button :class="{ active: capabilityDomain === 'script' }" @click="capabilityDomain = 'script'">剧本</button></div></header><button v-for="role in ['director', 'architect', 'writer', 'reviewer']" :key="role" :class="{ active: selectedRole === role }" @click="selectedRole = role"><span><strong>{{ roleMeta[role].name }}</strong><small>{{ roleMeta[role].responsibility }}</small></span><em>{{ skillNamesForRole(role).length }} Skills</em></button></aside>
          <main class="skill-governance">
            <header class="selected-agent-summary"><div><p class="eyebrow">Selected Agent · {{ capabilityDomain === 'novel' ? '小说域' : '剧本域' }}</p><h2>{{ roleMeta[selectedRole].name }}</h2><p>{{ roleMeta[selectedRole].responsibility }}</p></div><div class="agent-runtime-counts"><span><strong>{{ selectedRoleSkillNames.size }}</strong>本领域 Skills</span><span><strong>{{ toolGroups.filter(group => mountEnabled(selectedRole, group.id)).length }}</strong>已挂载工具组</span></div></header>
            <section class="skill-library"><header><div><p class="eyebrow">Skill Registry</p><h2>Skills 技能库</h2><small>来自仓库真实 SKILL.md；匹配标签决定它可被哪些角色、阶段与创作方向选中。</small></div><label><PhFunnel /><select v-model="skillDomain"><option value="all">全部领域</option><option value="platform">平台共享</option><option value="script">剧本</option><option value="novel">小说</option></select></label></header><div class="skill-card-grid"><article v-for="skill in filteredSkills" :key="skill.name" :class="{ mounted: selectedRoleSkillNames.has(skill.name) }"><header><span>{{ skill.domain }}</span><em>{{ skill.admission_status === 'admitted' ? `已准入 · ${skill.admission_cases.length} 项评测` : selectedRoleSkillNames.has(skill.name) ? '核心挂载' : skill.roles.length ? '孵化中' : '基础能力' }}</em></header><strong>{{ skill.name }}</strong><p>{{ skill.description }}</p><div v-if="skill.roles.length || skill.stages.length || skill.genres.length || skill.themes.length || skill.styles.length || skill.structures.length" class="skill-match-tags"><span v-for="role in skill.roles" :key="`role-${role}`">角色 · {{ role }}</span><span v-for="stage in skill.stages" :key="`stage-${stage}`">阶段 · {{ stage }}</span><span v-for="genre in skill.genres" :key="`genre-${genre}`">题材 · {{ genre }}</span><span v-for="theme in skill.themes" :key="`theme-${theme}`">主题 · {{ theme }}</span><span v-for="style in skill.styles" :key="`style-${style}`">风格 · {{ style }}</span><span v-for="structure in skill.structures" :key="`structure-${structure}`">结构 · {{ structure }}</span></div><footer><small>优先级 {{ skill.selection_priority }} · {{ skill.references.length ? `${skill.references.length} 个参考资源` : '无外部参考' }}</small><button :disabled="busy" @click="openSkillEditor(skill)"><PhPencilSimple />修改</button></footer></article><p v-if="!filteredSkills.length" class="empty-state">该领域尚未发现 Skills。请检查 SKILL.md 目录与 frontmatter。</p></div></section>
            <section class="tool-governance"><header><div><p class="eyebrow">Execution Tools</p><h2>工具组与运行时挂载</h2><small>Tool 才能读取项目、提交候选或调用外部服务；切换只影响下一次 Agent 运行。</small></div></header><div v-if="toolGroups.length" class="tool-group-list"><article v-for="group in toolGroups" :key="group.id"><div><span :class="group.enabled ? 'status-connected' : 'status-suspended'">{{ group.enabled ? '可用' : '停用' }}</span><strong>{{ group.name }}</strong><small>{{ group.tool_keys.join(' · ') }}</small></div><button :class="{ active: mountEnabled(selectedRole, group.id) }" :disabled="busy || !group.enabled" @click="toggleMount(selectedRole, group)">{{ mountEnabled(selectedRole, group.id) ? '已挂载' : '挂载到角色' }}</button></article></div><div v-else class="tool-empty"><PhWarningCircle /><div><strong>尚未登记工具组</strong><p>当前 Agent 只有 Skills 方法论，没有可治理的执行工具。需要先把领域 FunctionTool 或 MCP 白名单封装为 Tool Group。</p></div></div></section>
            <section class="skill-plan-audit"><header><div><p class="eyebrow">Runtime Explainability</p><h2>最近 SkillPlan</h2><small>每次运行固定 CreativeProfile 与选用 Skill；后续修改技能不会悄悄改变历史运行。</small></div></header><div v-if="runtimeSkillPlans.length" class="skill-plan-list"><article v-for="item in runtimeSkillPlans" :key="item.run_id"><header><div><strong>{{ item.project_name }}</strong><small>{{ formatDate(item.created_at) }} · Run {{ item.run_id.slice(0, 8) }}</small></div><span>{{ item.plan.medium }} · {{ item.plan.role_key }} · {{ item.plan.stage }}</span></header><div class="skill-plan-profile"><span v-for="genre in item.plan.creative_profile.genres" :key="`plan-genre-${genre}`">题材 {{ genre }}</span><span v-for="theme in item.plan.creative_profile.themes" :key="`plan-theme-${theme}`">主题 {{ theme }}</span><span v-for="style in item.plan.creative_profile.styles" :key="`plan-style-${style}`">风格 {{ style }}</span><span v-for="structure in item.plan.creative_profile.structures" :key="`plan-structure-${structure}`">结构 {{ structure }}</span></div><ol><li v-for="selection in item.plan.selections" :key="selection.key"><div><strong>{{ selection.key }}</strong><span>{{ selection.layer }} · {{ selection.score }} 分</span></div><p>{{ selection.reasons.join('；') }}</p></li></ol></article></div><p v-else class="empty-state">新运行将在这里显示真实 SkillPlan；已有历史运行若未保存该快照，不会补造解释数据。</p></section>
          </main>
        </section>
      </template>
      <template v-else-if="activeView === 'mcp'">
        <div class="supply-actions"><button class="primary" @click="mcpOpen = true">＋ 注册 MCP Server</button></div>
        <section class="governance-stack">
          <article class="tenant-panel"><header><div><p class="eyebrow">MCP Registry</p><h2>连接与工具发现</h2></div></header><div class="governance-cards"><div v-for="server in mcpServers" :key="server.id"><span :class="`status-${server.status}`">{{ server.status }}</span><strong>{{ server.name }}</strong><small>{{ server.transport }} · {{ server.min_tier_code }} · {{ server.latency_ms == null ? '未采样' : `${server.latency_ms} ms` }}</small><p v-if="server.last_error">{{ server.last_error }}</p><button :disabled="busy" @click="discoverMcp(server)">连接并重新发现</button></div><p v-if="!mcpServers.length" class="empty-state">尚未注册 MCP Server。</p></div></article>
          <article class="tenant-panel"><header><div><p class="eyebrow">Whitelist & Role Mount</p><h2>白名单与角色挂载</h2><small>批准只允许平台使用；挂载后才会进入指定角色的下一次运行快照。</small></div><label>目标角色<select v-model="selectedRole"><option v-for="role in ['director', 'architect', 'writer', 'reviewer']" :key="role" :value="role">{{ roleMeta[role].name }}</option></select></label></header><div class="table-wrap"><table><thead><tr><th>工具</th><th>Server</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="tool in mcpTools" :key="tool.id"><td><strong>{{ tool.name }}</strong><small>{{ tool.description }}</small></td><td>{{ mcpServers.find(item => item.id === tool.server_id)?.name }}</td><td><span :class="tool.whitelisted ? 'status-connected' : 'status-unconfigured'">{{ tool.whitelisted ? '已批准' : '默认拒绝' }}</span><small v-if="mcpServers.find(item => item.id === tool.server_id)?.confirmation_required">等待确认续跑能力</small></td><td><button @click="toggleWhitelist(tool)">{{ tool.whitelisted ? '移出白名单' : '批准' }}</button><button :disabled="busy || !tool.whitelisted || mcpServers.find(item => item.id === tool.server_id)?.confirmation_required" @click="packageMcpTool(tool)">挂载到{{ roleMeta[selectedRole].name }}</button></td></tr></tbody></table><p v-if="!mcpTools.length" class="empty-state">连接 Server 并发现工具后，才能进行白名单与角色挂载。</p></div></article>
          <article class="tenant-panel"><header><div><p class="eyebrow">Sandbox Policy</p><h2>默认执行策略</h2></div><small>当前 v{{ sandboxPolicies.find(item => item.key === 'default')?.version ?? 0 }}</small></header><div class="policy-options"><button v-for="mode in ['direct', 'sandbox', 'sandbox_confirm'] as const" :key="mode" :class="{ active: sandboxPolicies.find(item => item.key === 'default')?.mode === mode }" @click="setSandbox(mode)">{{ mode }}</button></div></article>
        </section>
      </template>
      <template v-else>
        <section class="governance-stack memory-view">
          <article class="tenant-panel"><header><div><p class="eyebrow">Memory Policies</p><h2>角色级策略</h2></div><small>创作决策强制保留</small></header><div class="governance-cards"><button v-for="policy in displayedMemoryPolicies" :key="policy.role_key" @click="policyEditing = { ...policy }"><span class="status-connected">v{{ policy.version }}</span><strong>{{ policy.role_key }}</strong><small>{{ formatNumber(policy.memory_max_tokens) }} tokens · {{ policy.trigger_ratio * 100 }}% 触发</small></button></div></article>
          <article class="tenant-panel"><header><div><p class="eyebrow">Long-term Memory</p><h2>内容浏览与治理</h2></div><small>{{ memoryEntries.length }} 条</small></header><div class="memory-list"><article v-for="entry in memoryEntries" :key="entry.id"><header><div><strong>{{ entry.project_name }} · {{ entry.role_key }}</strong><small>{{ entry.tenant_name }} · {{ formatDate(entry.updated_at) }}</small></div><span>{{ entry.content_hash.slice(0, 8) }}</span></header><p>{{ entry.content }}</p><footer><button @click="editMemory(entry, 'correct')">纠偏</button><button @click="editMemory(entry, 'compress')">压缩</button><button class="danger" @click="deleteMemory(entry)">删除</button></footer></article><p v-if="!memoryEntries.length" class="empty-state">当前没有长期记忆。</p></div></article>
          <article class="tenant-panel"><header><div><p class="eyebrow">Append-only Audit</p><h2>记忆操作审计</h2></div></header><div class="audit-stream"><p v-for="item in memoryAudit" :key="item.id"><span>{{ item.operation }}</span><strong>{{ item.memory_entry_id.slice(0, 8) }}</strong><small>{{ formatDate(item.created_at) }}</small></p></div></article>
        </section>
      </template>
    </section>
    <div v-if="grantTenant" class="admin-modal-backdrop" @click.self="grantTenant = null"><form class="admin-modal" @submit.prevent="submitGrant"><header><div><p class="eyebrow">运营赠点</p><h2>{{ grantTenant.name }}</h2></div><button type="button" @click="grantTenant = null">×</button></header><p>赠送点数进入 {{ grantTenant.tier_name }} 作用域的永久余额，并同时生成订单、账本和审计记录。</p><label>点数数量<input v-model.number="grantTokens" type="number" min="1" max="10000000" required /></label><label>运营备注<input v-model="grantNote" maxlength="500" required /></label><footer><button type="button" @click="grantTenant = null">取消</button><button class="grant-confirm" :disabled="busy">{{ busy ? '处理中…' : '确认赠点' }}</button></footer></form></div>
    <div v-if="createOpen" class="admin-modal-backdrop" @click.self="createOpen = false"><form class="admin-modal" @submit.prevent="submitCreate"><header><div><p class="eyebrow">Tenant Provisioning</p><h2>创建租户</h2></div><button type="button" @click="createOpen = false">×</button></header><p>创建个人工作室、所有者账户和首个等级额度账户。</p><label>工作室名称<input v-model="createName" maxlength="200" required /></label><label>所有者邮箱<input v-model="createEmail" type="email" maxlength="320" required /></label><label>临时密码<input v-model="createPassword" type="password" minlength="12" required /></label><label>初始等级<select v-model="createTier"><option v-for="tier in tiers" :key="tier.code" :value="tier.code">{{ tier.name }} · {{ formatNumber(tier.monthly_token_quota) }} tokens</option></select></label><footer><button type="button" @click="createOpen = false">取消</button><button class="grant-confirm" :disabled="busy">{{ busy ? '创建中…' : '确认创建' }}</button></footer></form></div>
    <div v-if="tierTenant" class="admin-modal-backdrop" @click.self="tierTenant = null"><form class="admin-modal" @submit.prevent="submitTier"><header><div><p class="eyebrow">Tier Change</p><h2>{{ tierTenant.name }}</h2></div><button type="button" @click="tierTenant = null">×</button></header><p>旧等级点数仍保留在原作用域；新等级使用独立额度账户，变更即时影响 Creator 模型可见性。</p><label>目标等级<select v-model="targetTier"><option v-for="tier in tiers" :key="tier.code" :value="tier.code">{{ tier.name }} · {{ formatNumber(tier.monthly_token_quota) }} tokens</option></select></label><label>调整原因<input v-model="tierNote" maxlength="500" required /></label><footer><button type="button" @click="tierTenant = null">取消</button><button class="grant-confirm" :disabled="busy">{{ busy ? '处理中…' : '确认改级' }}</button></footer></form></div>
    <div v-if="providerOpen" class="admin-modal-backdrop" @click.self="providerOpen = false"><form class="admin-modal wide-modal provider-editor" @submit.prevent="submitProvider"><header><div><p class="eyebrow">服务商安全配置</p><h2>{{ providerKey ? '配置模型服务商' : '新增模型服务商' }}</h2></div><button type="button" aria-label="关闭" @click="providerOpen = false">×</button></header><p>连接信息与凭据分区保存。API 密钥提交后使用认证加密，页面和日志均不回显明文。</p><div class="editor-grid"><fieldset><legend>服务商连接</legend><label>服务商标识<small>平台内部使用的唯一英文标识，例如 aliyun；不是 API Key</small><input v-model="providerKey" pattern="[a-z0-9_-]+" required /></label><label>显示名称<input v-model="providerName" required /></label><label>接口地址（Base URL）<small>填写服务商提供的兼容接口根地址</small><input v-model="providerBaseUrl" type="url" /></label></fieldset><fieldset><legend>安全凭据</legend><label>API 密钥<small>保存后不会再次显示；重新配置时必须输入新值</small><input v-model="providerCredential" type="password" autocomplete="new-password" required /></label><div class="security-note"><PhCheckCircle />API 密钥将使用带认证加密保存，并记录密钥版本。</div></fieldset></div><footer><button type="button" @click="providerOpen = false">取消</button><button class="grant-confirm" :disabled="busy">{{ busy ? '连接中…' : '保存并连接' }}</button></footer></form></div>
    <div v-if="providerDeleteTarget" class="admin-modal-backdrop" @click.self="providerDeleteTarget = null"><section class="admin-modal confirm-modal"><header><div><p class="eyebrow">Destructive Action</p><h2>删除 {{ providerDeleteTarget.name }}？</h2></div><button type="button" aria-label="关闭" @click="providerDeleteTarget = null">×</button></header><p>将删除 Provider 凭据和其下 {{ supplyModels.filter(model => model.provider_id === providerDeleteTarget?.id).length }} 个模型。若模型仍被 Agent 模板或项目配置引用，系统会阻止删除并说明原因。</p><div class="delete-warning"><PhWarningCircle />此操作不可撤销，审计日志会永久保留。</div><footer><button type="button" @click="providerDeleteTarget = null">取消</button><button class="danger-confirm" :disabled="busy" @click="deleteProvider">{{ busy ? '删除中…' : '确认删除' }}</button></footer></section></div>
    <div v-if="skillEditing" class="admin-modal-backdrop" @click.self="skillEditing = null"><form class="admin-modal wide-modal skill-editor" @submit.prevent="submitSkill"><header><div><p class="eyebrow">Skill Governance · {{ skillEditing.domain }}</p><h2>修改 {{ skillEditing.name }}</h2></div><button type="button" aria-label="关闭" @click="skillEditing = null">×</button></header><p>名称、领域和参考路径由运行时契约锁定。这里修改的内容会直接写回 SKILL.md，并在下一次 Agent 构建时生效。</p><div class="skill-readonly-meta"><span><strong>领域</strong>{{ skillEditing.domain }}</span><span><strong>Digest</strong>{{ skillEditing.digest.slice(0, 12) }}</span><span><strong>参考资源</strong>{{ skillEditing.references.length }}</span></div><label>技能说明<small>用于技能目录和 Agent 渐进披露索引</small><textarea v-model="skillDescription" rows="3" maxlength="1000" required /></label><label>指令正文<small>Markdown 内容；保存时会重新校验引用路径与完整性</small><textarea v-model="skillInstructions" rows="16" maxlength="100000" required /></label><footer><button type="button" @click="skillEditing = null">取消</button><button class="grant-confirm" :disabled="busy">{{ busy ? '校验并保存中…' : '保存 Skill' }}</button></footer></form></div>
    <div v-if="modelOpen" class="admin-modal-backdrop" @click.self="modelOpen = false"><form class="admin-modal wide-modal model-editor" @submit.prevent="submitModel"><header><div><p class="eyebrow">Model Supply</p><h2>{{ supplyModels.some(item => item.key === modelKey) ? '配置模型' : '新增模型' }}</h2></div><button type="button" aria-label="关闭" @click="modelOpen = false">×</button></header><div class="editor-grid"><fieldset><legend>身份与运行时</legend><label>模型 Key<small>应与 Provider 的模型标识完全一致</small><input v-model="modelKey" required /></label><label>显示名称<input v-model="modelName" required /></label><label>Provider<select v-model="modelProvider" required><option v-for="provider in providers" :key="provider.id" :value="provider.id">{{ provider.name }}</option></select></label><label>AgentScope Class<small>AgentFactory 实例化模型时使用</small><input v-model="modelClass" required /></label></fieldset><fieldset><legend>价格与授权</legend><label>最低等级<select v-model="modelTier"><option v-for="tier in tiers" :key="tier.code" :value="tier.code">{{ tier.name }} · rank {{ tier.rank }}</option></select></label><div class="modal-split"><label>输入价 / 百万 Tokens<input v-model.number="modelInputPrice" type="number" min="0" step="0.0001" /></label><label>输出价 / 百万 Tokens<input v-model.number="modelOutputPrice" type="number" min="0" step="0.0001" /></label></div><label class="check-line availability-switch"><input v-model="modelEnabled" type="checkbox" /><span><strong>允许 Creator 使用</strong><small>关闭后新运行无法选择此模型，已有快照不受影响</small></span></label></fieldset></div><footer><button type="button" @click="modelOpen = false">取消</button><button class="grant-confirm" :disabled="busy">{{ busy ? '保存中…' : '保存模型' }}</button></footer></form></div>
    <div v-if="imageModelOpen" class="admin-modal-backdrop" @click.self="imageModelOpen = false"><form class="admin-modal wide-modal model-editor" @submit.prevent="submitImageModel"><header><div><p class="eyebrow">Image Model Supply</p><h2>配置生图模型</h2></div><button type="button" aria-label="关闭" @click="imageModelOpen = false">×</button></header><p>第三方代理凭据来自所选 Provider；封面 Prompt 由包装 Agent 根据作品信息生成。</p><div class="editor-grid"><fieldset><legend>模型与代理</legend><label>模型 Key<input v-model="imageModelKey" required /></label><label>显示名称<input v-model="imageModelName" required /></label><label>Provider<select v-model="imageModelProvider" required><option v-for="provider in providers" :key="provider.id" :value="provider.id">{{ provider.name }}</option></select></label><label>代理协议<select v-model="imageModelProtocol"><option value="grsai_image2">Grsai GPT Image 2</option><option value="openai_images">OpenAI Images Compatible</option></select></label><label>生成端点<input v-model="imageModelEndpoint" required /></label></fieldset><fieldset><legend>生成默认值与授权</legend><label>默认比例 / 像素<input v-model="imageModelAspectRatio" placeholder="1024x1024" required /></label><label>回复方式<select v-model="imageModelReplyType"><option value="json">JSON 同步</option><option value="async">异步轮询</option></select></label><label>最低等级<select v-model="imageModelTier"><option v-for="tier in tiers" :key="tier.code" :value="tier.code">{{ tier.name }} · rank {{ tier.rank }}</option></select></label><label>单张价格<input v-model.number="imageModelPrice" type="number" min="0" step="0.0001" /></label><label class="check-line availability-switch"><input v-model="imageModelEnabled" type="checkbox" /><span><strong>允许生成封面</strong><small>关闭后保留历史封面，新请求不可使用</small></span></label></fieldset></div><footer><button type="button" @click="imageModelOpen = false">取消</button><button class="grant-confirm" :disabled="busy">{{ busy ? '保存中…' : '保存生图模型' }}</button></footer></form></div>
    <div v-if="tierConfig" class="admin-modal-backdrop" @click.self="tierConfig = null"><form class="admin-modal" @submit.prevent="submitTierConfig"><header><div><p class="eyebrow">Tier Governance</p><h2>{{ tierConfig.code }}</h2></div><button type="button" @click="tierConfig = null">×</button></header><label>显示名称<input v-model="tierConfigName" required /></label><div class="modal-split"><label>Rank<input v-model.number="tierConfigRank" type="number" min="0" /></label><label>月费<input v-model.number="tierConfigPrice" type="number" min="0" step="0.01" /></label></div><label>月度 Tokens<input v-model.number="tierConfigQuota" type="number" min="0" /></label><label class="check-line"><input v-model="tierConfigEnabled" type="checkbox" />启用该等级</label><footer><button type="button" @click="tierConfig = null">取消</button><button class="grant-confirm" :disabled="busy">保存 Tier</button></footer></form></div>
    <div v-if="mcpOpen" class="admin-modal-backdrop" @click.self="mcpOpen = false"><form class="admin-modal" @submit.prevent="submitMcp"><header><div><p class="eyebrow">MCP Registry</p><h2>注册 Server</h2></div><button type="button" @click="mcpOpen = false">×</button></header><p>完整 headers/env 将认证加密保存，页面仅显示去密后的公共摘要。</p><label>Server Key<input v-model="mcpKey" pattern="[a-z0-9_-]+" required /></label><label>显示名称<input v-model="mcpName" required /></label><label>传输<select v-model="mcpTransport"><option value="http">Streamable HTTP</option><option value="stdio">StdIO</option></select></label><label>{{ mcpTransport === 'http' ? 'URL' : 'Command' }}<input v-model="mcpEndpoint" required /></label><label>最低等级<select v-model="mcpTier"><option v-for="tier in tiers" :key="tier.code" :value="tier.code">{{ tier.name }}</option></select></label><div class="modal-split"><label>Secret 名称<input v-model="mcpSecretName" /></label><label>Secret 值<input v-model="mcpSecretValue" type="password" autocomplete="new-password" /></label></div><label class="toggle"><input v-model="mcpConfirmationRequired" type="checkbox" />每次外部调用前需要创作者确认<small>当前确认续跑链尚未开放。可信只读 Server 可关闭；写入、下载和携带作品内容的工具必须保持开启。</small></label><footer><button type="button" @click="mcpOpen = false">取消</button><button class="grant-confirm" :disabled="busy">加密保存</button></footer></form></div>
    <div v-if="memoryEditing" class="admin-modal-backdrop" @click.self="memoryEditing = null"><form class="admin-modal wide-modal" @submit.prevent="submitMemory"><header><div><p class="eyebrow">Memory {{ memoryOperation }}</p><h2>{{ memoryEditing.project_name }} · {{ memoryEditing.role_key }}</h2></div><button type="button" @click="memoryEditing = null">×</button></header><label>记忆内容<textarea v-model="memoryContent" rows="12" maxlength="100000" required /></label><footer><button type="button" @click="memoryEditing = null">取消</button><button class="grant-confirm" :disabled="busy">{{ memoryOperation === 'compress' ? '确认压缩' : '保存纠偏' }}</button></footer></form></div>
    <div v-if="policyEditing" class="admin-modal-backdrop" @click.self="policyEditing = null"><form class="admin-modal" @submit.prevent="submitMemoryPolicy"><header><div><p class="eyebrow">Memory Policy</p><h2>{{ policyEditing.role_key }}</h2></div><button type="button" @click="policyEditing = null">×</button></header><label>最大 Tokens<input v-model.number="policyEditing.memory_max_tokens" type="number" min="100" /></label><div class="modal-split"><label>压缩触发比例<input v-model.number="policyEditing.trigger_ratio" type="number" min="0.01" max="1" step="0.01" /></label><label>保留比例<input v-model.number="policyEditing.reserve_ratio" type="number" min="0" max="0.99" step="0.01" /></label></div><label>记忆指令<textarea v-model="policyEditing.memory_instructions" rows="6" required /></label><label class="check-line"><input type="checkbox" checked disabled />创作决策强制保留（不可关闭）</label><footer><button type="button" @click="policyEditing = null">取消</button><button class="grant-confirm" :disabled="busy">保存策略</button></footer></form></div>
  </div>
</template>
