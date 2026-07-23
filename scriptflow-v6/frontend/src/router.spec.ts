// @vitest-environment jsdom

import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'

const routes = [
  { path: '/', name: 'dashboard', component: { template: '<span />' } },
  { path: '/projects/:projectId/:space/:groupId?/:unitId?', name: 'workspace', component: { template: '<span />' } },
]

describe('workspace routes', () => {
  it('preserves project, creator space, group and unit in a deep link', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes })
    await router.push('/projects/10/work/1/8')
    expect(router.currentRoute.value.name).toBe('workspace')
    expect(router.currentRoute.value.params).toMatchObject({
      projectId: '10', space: 'work', groupId: '1', unitId: '8',
    })
  })

  it('supports story and review spaces without requiring a selected unit', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes })
    await router.push('/projects/10/story')
    expect(router.currentRoute.value.params).toMatchObject({ projectId: '10', space: 'story' })
    await router.push('/projects/10/review')
    expect(router.currentRoute.value.params.space).toBe('review')
  })
})
