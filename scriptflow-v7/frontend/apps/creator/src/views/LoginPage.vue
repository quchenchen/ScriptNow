<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useLocale } from '@scriptflow/shared'

import { ApiError } from '../api'
import { safeNextPath } from '../navigation'
import { useSessionStore } from '../stores/session'

const email = ref('')
const password = ref('')
const error = ref('')
const submitting = ref(false)
const session = useSessionStore()
const route = useRoute()
const router = useRouter()
const { t, toggleLocale } = useLocale()

async function submit() {
  error.value = ''
  submitting.value = true
  try {
    await session.login(email.value, password.value)
    await router.push(safeNextPath(route.query.next))
  } catch (caught) {
    error.value = caught instanceof ApiError ? caught.message : t('auth.failure')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="auth-layout">
    <section class="auth-story">
      <span class="growth-mark">S</span>
      <p class="eyebrow">{{ t('auth.creatorEyebrow') }}</p>
      <h1 class="preserve-lines">{{ t('auth.hero') }}</h1>
      <p>{{ t('auth.description') }}</p>
    </section>
    <form class="auth-card" @submit.prevent="submit">
      <div>
        <p class="eyebrow">{{ t('auth.welcomeBack') }}</p>
        <h2>{{ t('auth.enterSpace') }}</h2>
      </div>
      <label>{{ t('common.email') }}<input v-model="email" type="email" autocomplete="email" required /></label>
      <label>{{ t('common.password') }}<input v-model="password" type="password" autocomplete="current-password" minlength="12" required /></label>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <button class="primary" :disabled="submitting">{{ submitting ? t('auth.entering') : t('auth.enter') }}</button>
      <p class="muted tiny">{{ t('auth.security') }}</p>
      <button class="locale-switch auth-locale-switch" type="button" :aria-label="t('locale.label')" @click="toggleLocale">{{ t('locale.action') }}</button>
    </form>
  </main>
</template>
