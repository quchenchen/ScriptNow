<script setup lang="ts">
import { useLocale } from '@scriptflow/shared'

const { t, toggleLocale } = useLocale()
</script>

<template>
  <main class="welcome-layout">
    <span class="growth-mark">S</span>
    <button class="locale-switch welcome-locale-switch" :aria-label="t('locale.label')" @click="toggleLocale">{{ t('locale.action') }}</button>
    <p class="eyebrow">{{ t('welcome.first') }}</p>
    <h1>{{ t('welcome.title') }}</h1>
    <p>{{ t('welcome.description') }}</p>
    <RouterLink class="primary link-button" to="/new">{{ t('welcome.create') }}</RouterLink>
  </main>
</template>
