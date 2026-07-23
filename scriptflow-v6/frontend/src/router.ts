import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: { template: '<span />' } },
    { path: '/projects/new', name: 'create-project', component: { template: '<span />' } },
    {
      path: '/projects/:projectId/:space/:groupId?/:unitId?',
      name: 'workspace',
      component: { template: '<span />' },
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
