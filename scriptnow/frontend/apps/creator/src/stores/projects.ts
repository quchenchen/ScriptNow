import { defineStore } from 'pinia'

import { api } from '../api'
import type { Medium, Project, SourceMode, WorkflowKind, WorkspaceFile } from '../types'

export const useProjectsStore = defineStore('projects', {
  state: () => ({ items: [] as Project[], loading: false }),
  actions: {
    async load() {
      this.loading = true
      try {
        this.items = await api<Project[]>('/projects')
      } finally {
        this.loading = false
      }
    },
    async create(input: {
      name: string
      medium: Medium
      sourceMode: SourceMode
      workflowKind?: WorkflowKind
      direction: Record<string, string>
    }) {
      const project = await api<Project>('/projects', {
        method: 'POST',
        body: JSON.stringify({
          name: input.name,
          medium: input.medium,
          source_mode: input.sourceMode,
          workflow_kind: input.workflowKind,
          direction: input.direction,
        }),
      })
      this.items.push(project)
      return project
    },
    async remove(projectId: string, confirmationName: string) {
      await api<void>(`/projects/${projectId}`, {
        method: 'DELETE',
        body: JSON.stringify({ confirmation_name: confirmationName }),
      })
      this.items = this.items.filter((item) => item.id !== projectId)
    },
    upload(projectId: string, file: File) {
      const body = new FormData()
      body.set('file', file)
      return api<WorkspaceFile>(`/projects/${projectId}/files`, { method: 'POST', body })
    },
    files(projectId: string) {
      return api<WorkspaceFile[]>(`/projects/${projectId}/files`)
    },
    deleteFile(projectId: string, fileId: string) {
      return api<void>(`/projects/${projectId}/files/${fileId}`, { method: 'DELETE' })
    },
  },
})
