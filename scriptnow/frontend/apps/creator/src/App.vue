<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { RouterView } from 'vue-router'
import { useLocale } from '@scriptnow/shared'

import { router } from './router'
import { useSessionStore } from './stores/session'

const session = useSessionStore()
const { locale } = useLocale()
function handleAuthExpired() {
  const next = router.currentRoute.value.fullPath
  session.user = null
  session.ready = true
  if (router.currentRoute.value.path !== '/login') {
    void router.replace({ path: '/login', query: { next } })
  }
}
onMounted(() => window.addEventListener('scriptnow:auth-expired', handleAuthExpired))
onUnmounted(() => window.removeEventListener('scriptnow:auth-expired', handleAuthExpired))
</script>

<template>
  <div v-ui-locale="locale" class="creator-locale-root">
    <div v-if="!session.ready" class="boot-screen" aria-live="polite">
      <img class="growth-mark" src="/scriptnow-mark.svg" alt="ScriptNow" />
      <p>正在恢复创作现场…</p>
    </div>
    <RouterView v-else />
  </div>
</template>
