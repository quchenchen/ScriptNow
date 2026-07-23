import { createRouter, createWebHistory } from 'vue-router'

import DashboardPage from './views/DashboardPage.vue'
import AccountPage from './views/AccountPage.vue'
import AgentTeamPage from './views/AgentTeamPage.vue'
import LoginPage from './views/LoginPage.vue'
import PackagingPage from './views/PackagingPage.vue'
import WelcomePage from './views/WelcomePage.vue'
import WizardPage from './views/WizardPage.vue'
import WorkspacePage from './views/WorkspacePage.vue'
import { useSessionStore } from './stores/session'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: LoginPage, meta: { public: true } },
    { path: '/welcome', component: WelcomePage },
    { path: '/', component: DashboardPage },
    { path: '/account', component: AccountPage },
    { path: '/new', component: WizardPage },
    { path: '/projects/:projectId', component: WorkspacePage },
    { path: '/projects/:projectId/agents', component: AgentTeamPage },
    { path: '/projects/:projectId/packaging', component: PackagingPage },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  const session = useSessionStore()
  if (!session.ready) await session.restore()
  if (!to.meta.public && !session.user) return { path: '/login', query: { next: to.fullPath } }
  if (to.path === '/login' && session.user) return '/'
})
