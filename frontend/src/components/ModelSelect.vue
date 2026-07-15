<template>
  <div class="model-select">
    <button class="trigger" @click="open = !open">
      <span class="dot" :class="{ active: currentProvider?.configured }"></span>
      <span>{{ currentLabel || '选择模型' }}</span>
      <span class="arrow">▾</span>
    </button>
    <div class="dropdown" v-if="open">
      <div class="search-box"><input v-model="search" placeholder="搜索模型…" /></div>
      <div v-for="p in filteredProviders" :key="p.provider_id" class="group">
        <div class="group-label">{{ p.provider_name }} <span v-if="!p.configured" class="no-key">未配置</span></div>
        <div v-for="m in p.models" :key="m.id"
          :class="['option', { active: model === m.id, disabled: !m.available }]"
          @click="selectModel(m)">
          <span>{{ m.name }}</span>
          <span class="type">{{ m.type }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

const model = defineModel<string>({ default: 'dashscope:deepseek-v4-pro' })
const open = ref(false)
const search = ref('')
const providers = ref<any[]>([])

onMounted(async () => {
  try { const { data } = await axios.get('/api/llm/providers'); providers.value = data.providers } catch {}
})

const filteredProviders = computed(() => {
  if (!search.value) return providers.value
  const q = search.value.toLowerCase()
  return providers.value.map((p: any) => ({
    ...p,
    models: p.models.filter((m: any) => m.name.toLowerCase().includes(q) || m.id.toLowerCase().includes(q))
  })).filter((p: any) => p.models.length)
})

const currentLabel = computed(() => {
  for (const p of providers.value)
    for (const m of p.models)
      if (m.id === model.value) return `${p.provider_name} · ${m.name}`
  return null
})

const currentProvider = computed(() => providers.value.find((p: any) =>
  p.models.some((m: any) => m.id === model.value)
))

function selectModel(m: any) {
  if (!m.available) return
  model.value = m.id; open.value = false
}
</script>

<style scoped>
.model-select { position: relative; font-size: 11px }
.trigger { display: flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: var(--r-md); border: 1px solid var(--bs); background: rgba(255,255,255,0.02); color: var(--t2); cursor: pointer; font-size: 11px; font-family: inherit }
.trigger:hover { border-color: var(--bw) }
.dot { width: 6px; height: 6px; border-radius: 50%; background: var(--t4) }
.dot.active { background: var(--green) }
.arrow { font-size: 8px; color: var(--t4); margin-left: 2px }
.dropdown { position: absolute; top: 100%; left: 0; margin-top: 4px; width: 280px; max-height: 340px; overflow-y: auto; background: var(--bg-panel); border: 1px solid var(--bw); border-radius: var(--r-lg); z-index: 100; box-shadow: 0 8px 24px rgba(0,0,0,0.4) }
.search-box { padding: 8px }
.search-box input { width: 100%; background: rgba(255,255,255,0.03); border: 1px solid var(--bs); border-radius: var(--r-md); padding: 6px 10px; color: var(--t1); font-size: 11px; outline: none; font-family: inherit }
.search-box input:focus { border-color: var(--accent) }
.group-label { padding: 6px 10px; font-size: 9px; font-weight: 590; color: var(--t4); text-transform: uppercase; letter-spacing: .04em; border-top: 1px solid var(--bs) }
.no-key { color: var(--amber); font-weight: 400; text-transform: none; letter-spacing: 0; margin-left: 4px }
.option { display: flex; align-items: center; justify-content: space-between; padding: 6px 10px; cursor: pointer; color: var(--t2); transition: background .1s }
.option:hover { background: var(--bg-hover) }
.option.active { background: var(--bg-active); color: var(--t1) }
.option.disabled { opacity: .4; cursor: default }
.option .type { font-size: 9px; color: var(--t4) }
</style>
