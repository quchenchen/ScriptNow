<template>
  <div class="login-page">
    <div class="login-card">
      <h1>ScriptFlow</h1>
      <p class="sub">AI Agent 剧本创作平台</p>

      <!-- Tab switch -->
      <div class="tabs">
        <button :class="{ active: mode === 'login' }" @click="mode = 'login'">登录</button>
        <button :class="{ active: mode === 'register' }" @click="mode = 'register'">注册</button>
      </div>

      <input v-model="username" placeholder="用户名 / 手机号" @keyup.enter="handleSubmit" />
      <input v-model="password" type="password" placeholder="密码" @keyup.enter="handleSubmit" />

      <button class="submit-btn" @click="handleSubmit" :disabled="loading">
        {{ loading ? '…' : mode === 'login' ? '登录' : '注册' }}
      </button>

      <p class="hint">{{ mode === 'register' ? '新用户注册送1天专家会员+100剧点' : '没有账号？切换到注册' }}</p>
      <p v-if="error" class="error">{{ error }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import axios from 'axios'

const emit = defineEmits(['login'])
const mode = ref<'login' | 'register'>('login')
const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function handleSubmit() {
  if (!username.value || !password.value) { error.value = '请填写用户名和密码'; return }
  loading.value = true; error.value = ''
  try {
    const endpoint = mode.value === 'login' ? '/api/auth/login' : '/api/auth/register'
    const { data } = await axios.post(endpoint, { username: username.value, password: password.value })
    emit('login', data)
  } catch (e: any) {
    error.value = e.response?.data?.detail || '操作失败'
  }
  loading.value = false
}
</script>

<style scoped>
.login-page { display: flex; align-items: center; justify-content: center; min-height: 100vh; background: var(--bg-root) }
.login-card { background: var(--bg-surface); border: 1px solid var(--bw); border-radius: 12px; padding: 40px; width: 360px; text-align: center }
.login-card h1 { font-size: 24px; font-weight: 590; color: var(--t1); margin-bottom: 4px }
.login-card .sub { font-size: 13px; color: var(--t3); margin-bottom: 20px }
.tabs { display: flex; gap: 0; margin-bottom: 16px; border-radius: var(--r-md); overflow: hidden; border: 1px solid var(--bs) }
.tabs button { flex: 1; padding: 8px; border: none; background: transparent; color: var(--t4); font-size: 13px; cursor: pointer; font-family: inherit; transition: all .15s }
.tabs button.active { background: var(--accent-bg); color: #fff }
.login-card input { width: 100%; background: rgba(255,255,255,0.03); border: 1px solid var(--bs); border-radius: var(--r-md); padding: 10px 12px; color: var(--t1); font-size: 14px; outline: none; margin-bottom: 10px; transition: border-color .15s }
.login-card input:focus { border-color: var(--accent) }
.login-card input::placeholder { color: var(--t4) }
.submit-btn { width: 100%; padding: 12px; border-radius: var(--r-md); background: var(--accent-bg); border: none; color: #fff; font-size: 15px; font-weight: 590; cursor: pointer }
.submit-btn:disabled { opacity: .5 }
.hint { font-size: 11px; color: var(--t4); margin-top: 12px }
.error { color: #ef4444; font-size: 12px; margin-top: 8px }
</style>
