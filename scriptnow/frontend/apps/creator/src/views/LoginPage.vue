<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useLocale, useTheme } from '@scriptnow/shared'
import {
  PhArrowDown,
  PhArrowUpRight,
  PhBookOpenText,
  PhCheckCircle,
  PhCompass,
  PhFilmScript,
  PhGraph,
  PhMoon,
  PhPencilLine,
  PhSun,
  PhUsersThree,
} from '@phosphor-icons/vue'

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
const { resolvedTheme, toggleTheme } = useTheme()
let revealObserver: IntersectionObserver | undefined

const workflow = [
  { key: 'direction', titleKey: 'auth.workflow.direction', bodyKey: 'auth.workflow.directionBody', icon: PhCompass },
  { key: 'blueprint', titleKey: 'auth.workflow.blueprint', bodyKey: 'auth.workflow.blueprintBody', icon: PhGraph },
  { key: 'writing', titleKey: 'auth.workflow.writing', bodyKey: 'auth.workflow.writingBody', icon: PhPencilLine },
  { key: 'review', titleKey: 'auth.workflow.review', bodyKey: 'auth.workflow.reviewBody', icon: PhCheckCircle },
] as const

const features = [
  { key: 'team', titleKey: 'auth.feature.team', bodyKey: 'auth.feature.teamBody', icon: PhUsersThree },
  { key: 'graph', titleKey: 'auth.feature.graph', bodyKey: 'auth.feature.graphBody', icon: PhGraph },
  { key: 'revision', titleKey: 'auth.feature.revision', bodyKey: 'auth.feature.revisionBody', icon: PhPencilLine },
] as const

onMounted(() => {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  revealObserver = new IntersectionObserver(
    (entries) => entries.forEach((entry) => entry.isIntersecting && entry.target.classList.add('is-visible')),
    { threshold: 0.16 },
  )
  document.querySelectorAll<HTMLElement>('[data-reveal]').forEach((element) => revealObserver?.observe(element))
})

onUnmounted(() => revealObserver?.disconnect())

function scrollToLogin() {
  document.querySelector('#login-card')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

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
  <main class="login-page">
    <section class="auth-layout">
      <section class="auth-story">
        <img class="growth-mark" src="/scriptnow-mark.svg" alt="ScriptNow" />
        <p class="eyebrow">{{ t('auth.creatorEyebrow') }}</p>
        <h1 class="preserve-lines">{{ t('auth.hero') }}</h1>
        <p>{{ t('auth.description') }}</p>
        <a class="auth-scroll-cue" href="#product-story">
          <span>{{ t('auth.discover') }}</span>
          <PhArrowDown aria-hidden="true" />
        </a>
      </section>
      <form id="login-card" class="auth-card" @submit.prevent="submit">
        <div>
          <p class="eyebrow">{{ t('auth.welcomeBack') }}</p>
          <h2>{{ t('auth.enterSpace') }}</h2>
        </div>
        <label>{{ t('common.email') }}<input v-model="email" type="email" autocomplete="email" required /></label>
        <label>{{ t('common.password') }}<input v-model="password" type="password" autocomplete="current-password" minlength="12" required /></label>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <button class="primary" :disabled="submitting">{{ submitting ? t('auth.entering') : t('auth.enter') }}</button>
        <div class="auth-interface-controls"><button class="theme-switch" type="button" :aria-label="resolvedTheme === 'dark' ? t('theme.light') : t('theme.dark')" @click="toggleTheme"><PhSun v-if="resolvedTheme === 'dark'" /><PhMoon v-else /></button><button class="locale-switch" type="button" :aria-label="t('locale.label')" @click="toggleLocale">{{ t('locale.action') }}</button></div>
      </form>
    </section>

    <section id="product-story" class="login-intro login-section">
      <div class="login-section-copy" data-reveal>
        <p class="eyebrow">{{ t('auth.introEyebrow') }}</p>
        <h2>{{ t('auth.introTitle') }}</h2>
        <p>{{ t('auth.introBody') }}</p>
      </div>
    </section>

    <section class="domain-showcase domain-novel login-section">
      <div class="domain-icon" data-reveal><PhBookOpenText aria-hidden="true" /></div>
      <div data-reveal>
        <p class="eyebrow">{{ t('auth.novelDomain') }}</p>
        <h2>{{ t('auth.novelPromise') }}</h2>
        <p>{{ t('auth.novelDescription') }}</p>
      </div>
      <span class="domain-index" aria-hidden="true">NOVEL</span>
    </section>

    <section class="domain-showcase domain-script login-section">
      <div class="domain-icon" data-reveal><PhFilmScript aria-hidden="true" /></div>
      <div data-reveal>
        <p class="eyebrow">{{ t('auth.scriptDomain') }}</p>
        <h2>{{ t('auth.scriptPromise') }}</h2>
        <p>{{ t('auth.scriptDescription') }}</p>
      </div>
      <span class="domain-index" aria-hidden="true">SCRIPT</span>
    </section>

    <section class="login-workflow login-section">
      <div class="login-section-copy" data-reveal>
        <p class="eyebrow">{{ t('auth.workflowEyebrow') }}</p>
        <h2>{{ t('auth.workflowTitle') }}</h2>
        <p>{{ t('auth.workflowBody') }}</p>
      </div>
      <ol class="workflow-track" data-reveal>
        <li v-for="(step, index) in workflow" :key="step.key">
          <span class="workflow-number">0{{ index + 1 }}</span>
          <component :is="step.icon" aria-hidden="true" />
          <strong>{{ t(step.titleKey) }}</strong>
          <p>{{ t(step.bodyKey) }}</p>
        </li>
      </ol>
    </section>

    <section class="login-features login-section">
      <div class="login-section-copy" data-reveal>
        <p class="eyebrow">{{ t('auth.featuresEyebrow') }}</p>
        <h2>{{ t('auth.featuresTitle') }}</h2>
      </div>
      <div class="feature-grid">
        <article v-for="feature in features" :key="feature.key" data-reveal>
          <component :is="feature.icon" aria-hidden="true" />
          <h3>{{ t(feature.titleKey) }}</h3>
          <p>{{ t(feature.bodyKey) }}</p>
        </article>
      </div>
    </section>

    <section class="login-closing login-section" data-reveal>
      <img class="growth-mark" src="/scriptnow-mark.svg" alt="" />
      <p class="eyebrow">{{ t('auth.closingEyebrow') }}</p>
      <h2>{{ t('auth.closingTitle') }}</h2>
      <button class="primary login-closing-action" type="button" @click="scrollToLogin">
        {{ t('auth.enter') }}
        <PhArrowUpRight aria-hidden="true" />
      </button>
    </section>
  </main>
</template>
