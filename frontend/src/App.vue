<template>
  <div id="app">
    <LoginPage v-if="!user" @login="onLogin" />
    <Dashboard v-else-if="!currentProject" :user="user" @select="onSelectProject" @logout="onLogout" @create="onCreateProject" />
    <Workspace v-else :user="user" :project="currentProject" @back="currentProject = null" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import LoginPage from './pages/LoginPage.vue'
import Dashboard from './pages/Dashboard.vue'
import Workspace from './pages/Workspace.vue'

const user = ref<any>(null)
const currentProject = ref<any>(null)

// Restore session from localStorage
onMounted(() => {
  const saved = localStorage.getItem('scriptflow_user')
  if (saved) {
    try { user.value = JSON.parse(saved) } catch { localStorage.removeItem('scriptflow_user') }
  }
})

function onLogin(u: any) {
  user.value = u
  localStorage.setItem('scriptflow_user', JSON.stringify(u))
}
function onLogout() {
  user.value = null
  currentProject.value = null
  localStorage.removeItem('scriptflow_user')
}
function onSelectProject(p: any) { currentProject.value = p }
function onCreateProject(p: any) { currentProject.value = p }
</script>

<style>
:root {
  --bg-root: #08090a; --bg-panel: #0f1011; --bg-surface: #191a1b;
  --bg-hover: rgba(255,255,255,0.04); --bg-active: rgba(255,255,255,0.06);
  --t1: #f7f8f8; --t2: #d0d6e0; --t3: #8a8f98; --t4: #62666d;
  --accent: #7170ff; --accent-bg: #5e6ad2;
  --bs: rgba(255,255,255,0.05); --bw: rgba(255,255,255,0.08);
  --green: #27a644; --amber: #eab308;
  --r-sm: 4px; --r-md: 6px; --r-lg: 8px;
  --font: 'Inter', system-ui, sans-serif;
}
* { box-sizing: border-box; margin: 0; padding: 0 }
body { font-family: var(--font); background: var(--bg-root); color: var(--t2); font-size: 13px; font-feature-settings: 'cv01','ss03'; -webkit-font-smoothing: antialiased }
#app { min-height: 100vh }
input, textarea, button { font-family: var(--font) }
</style>
