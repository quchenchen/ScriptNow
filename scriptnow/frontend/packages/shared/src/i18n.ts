import { computed, ref } from 'vue'

export type Locale = 'zh-CN' | 'en-US'

const STORAGE_KEY = 'scriptnow-ui-locale'
const LEGACY_STORAGE_KEY = 'scriptflow-ui-locale'
const storedLocale = typeof window === 'undefined'
  ? null
  : window.localStorage.getItem(STORAGE_KEY) ?? window.localStorage.getItem(LEGACY_STORAGE_KEY)
if (typeof window !== 'undefined' && storedLocale) {
  window.localStorage.setItem(STORAGE_KEY, storedLocale)
  window.localStorage.removeItem(LEGACY_STORAGE_KEY)
}
const initialLocale = storedLocale === 'en-US'
  ? 'en-US'
  : 'zh-CN'
const locale = ref<Locale>(initialLocale)

const messages = {
  'zh-CN': {
    'locale.label': '界面语言', 'locale.action': 'EN',
    'theme.label': '切换日夜模式', 'theme.light': '切换到日间模式', 'theme.dark': '切换到夜间模式',
    'brand.tagline': '让好故事长出来', 'common.saved': '已自动保存',
    'common.email': '邮箱', 'common.password': '密码', 'common.menu': '菜单',
    'creator.currentProject': '当前项目', 'creator.console': '项目控制台', 'creator.newProject': '创建新项目…',
    'creator.creation': '创作', 'creator.ideation': '创意发散', 'creator.blueprint': '蓝图规划', 'creator.storyGraph': '故事图谱', 'creator.storyMap': 'StoryMap',
    'creator.sceneWriting': '逐场写作', 'creator.chapterWriting': '逐章写作', 'creator.project': '项目',
    'creator.dashboard': '项目仪表盘', 'creator.team': '创作团队', 'creator.packaging': '作品包装',
    'creator.create': '创建项目', 'creator.export': '导出作品', 'creator.history': '历史版本', 'creator.workspace': '工作区',
    'creator.account': '账户与额度', 'creator.accountHint': '等级 · 点数 · 模型池', 'creator.script': '剧本', 'creator.novel': '小说',
    'auth.creatorEyebrow': 'ScriptNow Creator', 'auth.hero': '让故事在协作中\n自然生长。',
    'auth.description': '你给出方向，创作团队推进结构、写作与审读。剧本和小说拥有各自独立的创作逻辑。',
    'auth.welcomeBack': '欢迎回来', 'auth.enterSpace': '进入创作空间', 'auth.entering': '正在进入…',
    'auth.enter': '进入 ScriptNow',
    'auth.discover': '了解 ScriptNow',
    'auth.introEyebrow': '两种创作领域 · 一套协作体验', 'auth.introTitle': '作品不是被拼装出来的，而是在判断与修订中生长。',
    'auth.introBody': 'ScriptNow 将创作者的方向、Agent 团队的专业能力与可追溯的创作事实连接起来，让灵感能够扩展，也能够收束。',
    'auth.novelDomain': '小说创作', 'auth.novelPromise': '让人物欲望、关系变化与叙述声音持续生长',
    'auth.novelDescription': '从创意方向、小说蓝图、StoryMap 到逐章正文，保持人物动机与长线变化的一致，让每次人工修订成为后续写作的新事实。',
    'auth.scriptDomain': '剧本创作', 'auth.scriptPromise': '让场景行动、戏剧冲突与视听节奏彼此咬合',
    'auth.scriptDescription': '从核心命题、人物关系、场次节拍到标准格式正文，围绕可表演的行动推进，让结构、对白与镜头表达服务于同一戏剧目标。',
    'auth.workflowEyebrow': '从创意种子到可交付作品', 'auth.workflowTitle': '创作团队推进过程，你保留最终判断。',
    'auth.workflowBody': '每一步都有清晰产物、候选版本和人工决策边界。Agent 提议，创作者修订并采纳。',
    'auth.workflow.direction': '创意发散', 'auth.workflow.directionBody': '比较真正不同的故事方向，找到作品最值得生长的核心。',
    'auth.workflow.blueprint': '蓝图规划', 'auth.workflow.blueprintBody': '建立人物、世界、情节、关系与伏笔之间可验证的结构。',
    'auth.workflow.writing': '逐章创作', 'auth.workflow.writingBody': '依据最新修订版本持续写作，候选稿确认后才成为正文。',
    'auth.workflow.review': '质量审读', 'auth.workflow.reviewBody': '从结构、人物、节奏与表达中定位问题，让修订有据可循。',
    'auth.featuresEyebrow': '为真实创作过程设计', 'auth.featuresTitle': '看见故事如何变化，也看见每一次选择。',
    'auth.feature.team': '人格化创作团队', 'auth.feature.teamBody': '创意导演、故事建筑师、主笔与审读编辑在各自职责中协作，并共享已确认的创作上下文。',
    'auth.feature.graph': '故事图谱与时间线', 'auth.feature.graphBody': '用关系图谱和叙事时间线理解人物、事件、伏笔与世界规则，而不是面对一堆孤立条目。',
    'auth.feature.revision': '候选、修订与版本', 'auth.feature.revisionBody': '生成中只读预览，校验后允许人工修订；保存形成新版本，明确采纳后才进入作品正文。',
    'auth.closingEyebrow': '你的故事，你的最终决定', 'auth.closingTitle': '带着一个念头进来，让它长成一部作品。',
    'auth.failure': '暂时无法登录，请稍后重试。', 'welcome.first': '第一次来到 ScriptNow',
    'welcome.title': '先种下一颗故事的种子。', 'welcome.description': '选择小说或剧本、原创或改编，再告诉创作团队你希望故事朝哪里生长。',
    'welcome.create': '创建第一个项目',
    'admin.operations': '运营', 'admin.supply': '供给', 'admin.tenants': '租户与额度', 'admin.usage': '用量与成本',
    'admin.supplyManagement': '供给管理', 'admin.capabilities': 'Agent 团队与技能', 'admin.mcp': 'MCP 与沙箱', 'admin.memory': '记忆治理',
    'admin.logout': '退出管理台', 'admin.loginEyebrow': '管理员登录', 'admin.loginTitle': '进入 Console',
    'admin.loggingIn': '验证中…', 'admin.login': '安全登录', 'admin.hero': '平台治理台',
    'admin.heroDescription': '租户、供给、用量与 Agent 能力的统一运营界面。',
  },
  'en-US': {
    'locale.label': 'Interface language', 'locale.action': '中',
    'theme.label': 'Switch color theme', 'theme.light': 'Switch to light mode', 'theme.dark': 'Switch to dark mode',
    'brand.tagline': 'Let great stories grow', 'common.saved': 'Autosaved',
    'common.email': 'Email', 'common.password': 'Password', 'common.menu': 'Menu',
    'creator.currentProject': 'Current project', 'creator.console': 'Project dashboard', 'creator.newProject': 'Create new project…',
    'creator.creation': 'Create', 'creator.ideation': 'Ideation', 'creator.blueprint': 'Blueprint', 'creator.storyGraph': 'Story graph', 'creator.storyMap': 'StoryMap',
    'creator.sceneWriting': 'Scene writing', 'creator.chapterWriting': 'Chapter writing', 'creator.project': 'Project',
    'creator.dashboard': 'Project dashboard', 'creator.team': 'Creative team', 'creator.packaging': 'Work packaging',
    'creator.create': 'Create project', 'creator.export': 'Export work', 'creator.history': 'Version history', 'creator.workspace': 'Workspace',
    'creator.account': 'Account & usage', 'creator.accountHint': 'Tier · Credits · Models', 'creator.script': 'Script', 'creator.novel': 'Novel',
    'auth.creatorEyebrow': 'ScriptNow Creator', 'auth.hero': 'Let stories grow\nthrough collaboration.',
    'auth.description': 'You set the direction. Your creative team advances structure, writing, and review, with independent workflows for scripts and novels.',
    'auth.welcomeBack': 'Welcome back', 'auth.enterSpace': 'Enter your creative space', 'auth.entering': 'Entering…',
    'auth.enter': 'Enter ScriptNow',
    'auth.discover': 'Discover ScriptNow',
    'auth.introEyebrow': 'Two creative domains · One collaborative experience', 'auth.introTitle': 'A work is not assembled. It grows through judgment and revision.',
    'auth.introBody': 'ScriptNow connects your direction, the expertise of an Agent team, and traceable creative facts—giving ideas room to expand and a way to converge.',
    'auth.novelDomain': 'Novel creation', 'auth.novelPromise': 'Let desire, relationships, and narrative voice evolve across the work',
    'auth.novelDescription': 'From creative direction and blueprint to StoryMap and chapter prose, character motivation stays coherent—and every human revision becomes a fact for what follows.',
    'auth.scriptDomain': 'Script creation', 'auth.scriptPromise': 'Make action, dramatic conflict, and audiovisual rhythm work together',
    'auth.scriptDescription': 'From dramatic premise and relationships to scene beats and formatted pages, playable action keeps structure, dialogue, and visual expression aimed at the same dramatic goal.',
    'auth.workflowEyebrow': 'From creative seed to finished work', 'auth.workflowTitle': 'The creative team advances the process. You keep the final say.',
    'auth.workflowBody': 'Every stage has a clear deliverable, candidate versions, and a human decision boundary. Agents propose; creators revise and adopt.',
    'auth.workflow.direction': 'Explore directions', 'auth.workflow.directionBody': 'Compare genuinely different story engines and find the core worth growing.',
    'auth.workflow.blueprint': 'Plan the blueprint', 'auth.workflow.blueprintBody': 'Build a verifiable structure of characters, world, plot, relationships, and setups.',
    'auth.workflow.writing': 'Write progressively', 'auth.workflow.writingBody': 'Continue from the latest revision. A candidate becomes manuscript only after adoption.',
    'auth.workflow.review': 'Review quality', 'auth.workflow.reviewBody': 'Locate structural, character, pacing, and prose issues so every revision has a reason.',
    'auth.featuresEyebrow': 'Designed for real creative work', 'auth.featuresTitle': 'See how the story changes—and why each choice was made.',
    'auth.feature.team': 'A creative team with character', 'auth.feature.teamBody': 'The creative director, story architect, lead writer, and review editor collaborate within clear roles and shared confirmed context.',
    'auth.feature.graph': 'Story graph and timeline', 'auth.feature.graphBody': 'Understand characters, events, setups, and world rules through relationships and time—not as disconnected entries.',
    'auth.feature.revision': 'Candidates, revisions, versions', 'auth.feature.revisionBody': 'Generation streams as read-only, editing unlocks after validation, and only an explicit adoption changes the manuscript.',
    'auth.closingEyebrow': 'Your story. Your final decision.', 'auth.closingTitle': 'Bring in an idea. Let it grow into a work.',
    'auth.failure': 'Unable to sign in right now. Please try again shortly.', 'welcome.first': 'Your first time in ScriptNow',
    'welcome.title': 'Plant the first seed of a story.', 'welcome.description': 'Choose a novel or script, original or adaptation, then show the creative team where the story should grow.',
    'welcome.create': 'Create your first project',
    'admin.operations': 'Operations', 'admin.supply': 'Supply', 'admin.tenants': 'Tenants & quotas', 'admin.usage': 'Usage & costs',
    'admin.supplyManagement': 'Supply management', 'admin.capabilities': 'Agent team & skills', 'admin.mcp': 'MCP & sandbox', 'admin.memory': 'Memory governance',
    'admin.logout': 'Sign out', 'admin.loginEyebrow': 'Administrator sign-in', 'admin.loginTitle': 'Enter Console',
    'admin.loggingIn': 'Verifying…', 'admin.login': 'Secure sign-in', 'admin.hero': 'Platform governance',
    'admin.heroDescription': 'One operations workspace for tenants, supply, usage, and Agent capabilities.',
  },
} as const

export type MessageKey = keyof typeof messages['zh-CN']

function applyLocale(value: Locale) {
  locale.value = value
  if (typeof document !== 'undefined') document.documentElement.lang = value
  if (typeof window !== 'undefined') window.localStorage.setItem(STORAGE_KEY, value)
}

applyLocale(initialLocale)
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (event) => {
    if (event.key === STORAGE_KEY && (event.newValue === 'zh-CN' || event.newValue === 'en-US')) {
      locale.value = event.newValue
      document.documentElement.lang = event.newValue
    }
  })
}

export function useLocale() {
  return {
    locale: computed(() => locale.value),
    isEnglish: computed(() => locale.value === 'en-US'),
    t: (key: MessageKey) => messages[locale.value][key],
    setLocale: applyLocale,
    toggleLocale: () => applyLocale(locale.value === 'zh-CN' ? 'en-US' : 'zh-CN'),
  }
}
