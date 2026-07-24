<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'

import AppShell from '../components/AppShell.vue'
import { useAccountStore } from '../stores/account'
import { useProjectsStore } from '../stores/projects'
import { useSessionStore } from '../stores/session'

const account = useAccountStore()
const projects = useProjectsStore()
const session = useSessionStore()
const router = useRouter()
const referenceProject = computed(() => projects.items[0]?.id)
const percentage = computed(() => {
  if (!account.summary?.monthly_quota) return 0
  return Math.min(100, Math.round(account.summary.monthly_used / account.summary.monthly_quota * 100))
})
const formatNumber = (value: number) => new Intl.NumberFormat('zh-CN').format(value)

async function load() {
  if (!projects.items.length) await projects.load()
  await account.load(referenceProject.value)
}
async function logout() {
  await session.logout()
  await router.push('/login')
}
onMounted(() => void load())
</script>

<template>
  <AppShell title="账户中心" eyebrow="Membership & Usage">
    <div v-if="account.busy && !account.summary" class="studio-loading">正在读取等级与额度…</div>
    <template v-else-if="account.summary">
      <section class="account-hero">
        <div><p class="eyebrow">{{ account.summary.tenant_name }}</p><h2>{{ account.summary.tier_name }}</h2><p>月度额度优先消耗，耗尽后自动使用同等级点数。</p></div>
        <span>{{ account.summary.tier_code.toUpperCase() }}</span>
      </section>
      <section class="account-grid">
        <article class="quota-card"><p class="eyebrow">本月用量</p><strong>{{ formatNumber(account.summary.monthly_used) }} <small>/ {{ formatNumber(account.summary.monthly_quota) }} tokens</small></strong><div class="quota-track"><i :style="{ width: `${percentage}%` }" /></div><footer><span>剩余 {{ formatNumber(account.summary.monthly_remaining) }}</span><span>{{ percentage }}%</span></footer></article>
        <article class="quota-card"><p class="eyebrow">点数余额</p><strong>{{ formatNumber(account.summary.credits_available) }}</strong><p>点数长期有效，并受当前 {{ account.summary.tier_name }} 模型池约束。</p><button disabled class="secondary">购买点数包 · P8 后续</button></article>
      </section>
      <section class="model-pool"><header><div><p class="eyebrow">模型池</p><h2>本账户可用模型</h2></div><small>可见性由 Provider、模型状态与等级实时计算</small></header><div><article v-for="model in account.models" :key="model.id" :class="{ locked: !model.available }"><span data-i18n-skip>{{ model.provider_name }}</span><h3 data-i18n-skip>{{ model.display_name }}</h3><code data-i18n-skip>{{ model.key }}</code><p v-if="model.available">可用于下次 Agent 运行</p><p v-else-if="model.reason === 'upgrade_required'">🔒 升级至 {{ model.minimum_tier.toUpperCase() }} 解锁</p><p v-else>当前暂不可用</p></article></div></section>
      <button class="text-button account-logout" @click="logout">安全退出当前账户</button>
    </template>
  </AppShell>
</template>
