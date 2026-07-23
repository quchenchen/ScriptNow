<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { RouterView } from 'vue-router'

import { router } from './router'
import { useSessionStore } from './stores/session'

const session = useSessionStore()
function handleAuthExpired() {
  const next = router.currentRoute.value.fullPath
  session.user = null
  session.ready = true
  if (router.currentRoute.value.path !== '/login') {
    void router.replace({ path: '/login', query: { next } })
  }
}
onMounted(() => window.addEventListener('scriptflow:auth-expired', handleAuthExpired))
onUnmounted(() => window.removeEventListener('scriptflow:auth-expired', handleAuthExpired))
</script>

<template>
  <div v-if="!session.ready" class="boot-screen" aria-live="polite">
    <span class="growth-mark">S</span>
    <p>正在恢复创作现场…</p>
  </div>
  <RouterView v-else />
</template>
