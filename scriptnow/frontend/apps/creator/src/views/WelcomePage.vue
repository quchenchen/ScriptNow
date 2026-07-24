<script setup lang="ts">
import { useLocale, useTheme } from '@scriptnow/shared'
import { PhMoon, PhSun } from '@phosphor-icons/vue'

const { t, toggleLocale } = useLocale()
const { resolvedTheme, toggleTheme } = useTheme()
</script>

<template>
  <main class="welcome-layout">
    <img class="growth-mark" src="/scriptnow-mark.svg" alt="ScriptNow" />
    <div class="welcome-interface-controls"><button class="theme-switch" type="button" :aria-label="resolvedTheme === 'dark' ? t('theme.light') : t('theme.dark')" @click="toggleTheme"><PhSun v-if="resolvedTheme === 'dark'" /><PhMoon v-else /></button><button class="locale-switch" type="button" :aria-label="t('locale.label')" @click="toggleLocale">{{ t('locale.action') }}</button></div>
    <p class="eyebrow">{{ t('welcome.first') }}</p>
    <h1>{{ t('welcome.title') }}</h1>
    <p>{{ t('welcome.description') }}</p>
    <RouterLink class="primary link-button" to="/new">{{ t('welcome.create') }}</RouterLink>
  </main>
</template>
