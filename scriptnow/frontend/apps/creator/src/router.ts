import { createRouter, createWebHistory } from 'vue-router'

import { useSessionStore } from './stores/session'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: () => import('./views/LoginPage.vue'), meta: { public: true } },
    { path: '/welcome', component: () => import('./views/WelcomePage.vue') },
    { path: '/', component: () => import('./views/DashboardPage.vue') },
    { path: '/account', component: () => import('./views/AccountPage.vue') },
    { path: '/new', component: () => import('./views/WizardPage.vue') },
    { path: '/review-agent', component: () => import('./views/ReviewWorkbenchPage.vue') },
    { path: '/projects/:projectId', component: () => import('./views/WorkspacePage.vue') },
    { path: '/projects/:projectId/agents', component: () => import('./views/AgentTeamPage.vue') },
    { path: '/projects/:projectId/packaging', component: () => import('./views/PackagingPage.vue') },
    {
      path: '/projects/:projectId/review-agent',
      redirect: (to) => ({
        path: `/projects/${String(to.params.projectId)}`,
        query: { ...to.query, review: 'checkpoint' },
      }),
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  const session = useSessionStore()
  if (!session.ready) await session.restore()
  if (!to.meta.public && !session.user) return { path: '/login', query: { next: to.fullPath } }
  if (to.path === '/login' && session.user) return '/'
})
