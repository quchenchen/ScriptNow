import { computed, ref } from 'vue'

export type Locale = 'zh-CN' | 'en-US'

const STORAGE_KEY = 'scriptflow-ui-locale'
const initialLocale = typeof window !== 'undefined' && window.localStorage.getItem(STORAGE_KEY) === 'en-US'
  ? 'en-US'
  : 'zh-CN'
const locale = ref<Locale>(initialLocale)

const messages = {
  'zh-CN': {
    'locale.label': '界面语言', 'locale.action': 'EN',
    'brand.tagline': '让好故事长出来', 'common.saved': '已自动保存',
    'common.email': '邮箱', 'common.password': '密码', 'common.menu': '菜单',
    'creator.currentProject': '当前项目', 'creator.console': '项目控制台', 'creator.newProject': '创建新项目…',
    'creator.creation': '创作', 'creator.ideation': '创意发散', 'creator.blueprint': '蓝图规划', 'creator.storyGraph': '故事图谱', 'creator.storyMap': 'StoryMap',
    'creator.sceneWriting': '逐场写作', 'creator.chapterWriting': '逐章写作', 'creator.project': '项目',
    'creator.dashboard': '项目仪表盘', 'creator.team': '创作团队', 'creator.packaging': '作品包装',
    'creator.create': '创建项目', 'creator.export': '导出作品', 'creator.history': '历史版本', 'creator.workspace': '工作区',
    'creator.account': '账户与额度', 'creator.accountHint': '等级 · 点数 · 模型池', 'creator.script': '剧本', 'creator.novel': '小说',
    'auth.creatorEyebrow': 'ScriptFlow Creator', 'auth.hero': '让故事在协作中\n自然生长。',
    'auth.description': '你给出方向，创作团队推进结构、写作与审读。剧本和小说拥有各自独立的创作逻辑。',
    'auth.welcomeBack': '欢迎回来', 'auth.enterSpace': '进入创作空间', 'auth.entering': '正在进入…',
    'auth.enter': '进入 ScriptFlow', 'auth.security': '会话采用安全 Cookie，模型凭据不会发送到浏览器。',
    'auth.failure': '暂时无法登录，请稍后重试。', 'welcome.first': '第一次来到 ScriptFlow',
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
    'brand.tagline': 'Let great stories grow', 'common.saved': 'Autosaved',
    'common.email': 'Email', 'common.password': 'Password', 'common.menu': 'Menu',
    'creator.currentProject': 'Current project', 'creator.console': 'Project dashboard', 'creator.newProject': 'Create new project…',
    'creator.creation': 'Create', 'creator.ideation': 'Ideation', 'creator.blueprint': 'Blueprint', 'creator.storyGraph': 'Story graph', 'creator.storyMap': 'StoryMap',
    'creator.sceneWriting': 'Scene writing', 'creator.chapterWriting': 'Chapter writing', 'creator.project': 'Project',
    'creator.dashboard': 'Project dashboard', 'creator.team': 'Creative team', 'creator.packaging': 'Work packaging',
    'creator.create': 'Create project', 'creator.export': 'Export work', 'creator.history': 'Version history', 'creator.workspace': 'Workspace',
    'creator.account': 'Account & usage', 'creator.accountHint': 'Tier · Credits · Models', 'creator.script': 'Script', 'creator.novel': 'Novel',
    'auth.creatorEyebrow': 'ScriptFlow Creator', 'auth.hero': 'Let stories grow\nthrough collaboration.',
    'auth.description': 'You set the direction. Your creative team advances structure, writing, and review, with independent workflows for scripts and novels.',
    'auth.welcomeBack': 'Welcome back', 'auth.enterSpace': 'Enter your creative space', 'auth.entering': 'Entering…',
    'auth.enter': 'Enter ScriptFlow', 'auth.security': 'Your session uses secure cookies. Model credentials are never sent to the browser.',
    'auth.failure': 'Unable to sign in right now. Please try again shortly.', 'welcome.first': 'Your first time in ScriptFlow',
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
