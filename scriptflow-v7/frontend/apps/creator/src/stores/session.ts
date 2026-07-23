import { defineStore } from 'pinia'

import { api, ApiError } from '../api'
import type { Session } from '../types'

export const useSessionStore = defineStore('session', {
  state: () => ({ user: null as Session | null, ready: false }),
  actions: {
    async restore() {
      try {
        this.user = await api<Session>('/auth/me')
      } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 401) console.error(error)
        this.user = null
      } finally {
        this.ready = true
      }
    },
    async login(email: string, password: string) {
      this.user = await api<Session>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      })
    },
    async logout() {
      await api<void>('/auth/logout', { method: 'POST' })
      this.user = null
    },
  },
})
