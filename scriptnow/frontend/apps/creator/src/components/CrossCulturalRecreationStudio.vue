<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api, ApiError } from '../api'

type Artifact = {
  id: string
  kind:
    | 'source_story_model'
    | 'target_story_contract'
    | 'recreation_strategy'
    | 'pilot'
    | 'scale_plan'
  version: number
  ordinal: number
  status: 'candidate' | 'adopted' | 'superseded'
  payload: Record<string, any>
  feedback?: string | null
}

type RecreationState = {
  id: string
  project_id: string
  source_language: string
  target_language: string
  target_market: string
  target_audience: string
  distribution_context: string
  status: string
  artifacts: Artifact[]
  production_units: ProductionUnit[]
}

type ProductionUnit = {
  id: string
  scale_plan_artifact_id: string
  work_package_key: string
  version: number
  status: 'candidate' | 'adopted' | 'superseded'
  pipeline_status:
    | 'drafting'
    | 'validating'
    | 'review_pending'
    | 'revision_required'
    | 'ready_for_decision'
    | 'adopted'
    | 'failed'
  revision_kind: 'agent' | 'manual'
  source_unit_id?: string | null
  payload: Record<string, any>
  context_snapshot: Record<string, any>
  review_report?: {
    verdict: 'pass' | 'revise'
    findings: Array<{ severity: string; message: string }>
  } | null
  failure_reason?: string | null
  feedback?: string | null
}

type RecreationRun = {
  run_id: string
  status: 'queued' | 'running' | 'waiting' | 'succeeded' | 'failed' | 'cancelled'
  error_code?: string | null
}

const props = defineProps<{
  projectId: string
  direction: Record<string, string>
}>()
const route = useRoute()
const router = useRouter()

const state = ref<RecreationState | null>(null)
const loading = ref(true)
const running = ref('')
const error = ref('')
const feedback = ref('')
const genrePromise = ref('')
const backgroundPolicy = ref('')
const culturalDistance = ref('')
const protectedElements = ref('')
const allowedChanges = ref('')
const prohibitedChanges = ref('')
const activeStage = ref(1)
const stageInitialized = ref(false)
const selectedPackageKey = ref('')
const editingUnitId = ref('')
const editTitle = ref('')
const editDraft = ref('')
const exportOpen = ref(false)
const exportSelection = ref<string[]>([])

const sourceModel = computed(() =>
  state.value?.artifacts.find(
    (item) => item.kind === 'source_story_model' && item.status === 'adopted',
  ),
)
const targetContract = computed(() =>
  state.value?.artifacts.find(
    (item) => item.kind === 'target_story_contract' && item.status === 'adopted',
  ),
)
const strategies = computed(() =>
  state.value?.artifacts.filter(
    (item) => item.kind === 'recreation_strategy' && item.status !== 'superseded',
  ) ?? [],
)
const adoptedStrategy = computed(() =>
  strategies.value.find((item) => item.status === 'adopted'),
)
const pilots = computed(() =>
  state.value?.artifacts.filter(
    (item) => item.kind === 'pilot' && item.status !== 'superseded',
  ) ?? [],
)
const adoptedPilot = computed(() =>
  pilots.value.find((item) => item.status === 'adopted'),
)
const scalePlans = computed(() =>
  state.value?.artifacts.filter(
    (item) => item.kind === 'scale_plan' && item.status !== 'superseded',
  ) ?? [],
)
const adoptedScalePlan = computed(() =>
  scalePlans.value.find((item) => item.status === 'adopted'),
)
const currentProductionUnits = computed(() =>
  state.value?.production_units.filter(
    (item) => item.scale_plan_artifact_id === adoptedScalePlan.value?.id,
  ) ?? [],
)
const workPackages = computed<Record<string, any>[]>(
  () => adoptedScalePlan.value?.payload.work_packages ?? [],
)
const selectedWorkPackage = computed(
  () =>
    workPackages.value.find(
      (item) => String(item.order) === selectedPackageKey.value,
    ) ?? workPackages.value[0],
)
const selectedUnits = computed(() =>
  selectedWorkPackage.value
    ? productionUnitsFor(String(selectedWorkPackage.value.order))
    : [],
)
const selectedUnit = computed(
  () =>
    [...selectedUnits.value].sort((a, b) => b.version - a.version)[0] ?? null,
)
const adoptedProductionKeys = computed(
  () =>
    new Set(
      currentProductionUnits.value
        .filter((item) => item.status === 'adopted')
        .map((item) => item.work_package_key),
    ),
)
const productionComplete = computed(() => {
  const packages = adoptedScalePlan.value?.payload.work_packages ?? []
  return (
    packages.length > 0 &&
    packages.every((item: Record<string, any>) =>
      adoptedProductionKeys.value.has(String(item.order)),
    )
  )
})
const exportRows = computed(() =>
  workPackages.value.map((workPackage, index) => {
    const key = String(workPackage.order)
    const unit = currentProductionUnits.value.find(
      (item) => item.work_package_key === key && item.status === 'adopted',
    )
    return {
      key,
      chapterNumber: workPackage.chapter_number ?? index + 1,
      title: String(unit?.payload.title ?? workPackage.title ?? `第 ${index + 1} 章`),
      selectable: Boolean(unit),
      version: unit?.version,
    }
  }),
)

function productionUnitsFor(workPackageKey: string) {
  return currentProductionUnits.value.filter(
    (item) =>
      item.work_package_key === workPackageKey &&
      item.status !== 'superseded',
  )
}

function lines(value: string) {
  return value
    .split(/\n|[,，、]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

async function load() {
  state.value = await api<RecreationState>(
    `/cross-cultural-recreations/by-project/${props.projectId}`,
  )
  const contract = state.value.artifacts.find(
    (item) => item.kind === 'target_story_contract' && item.status === 'adopted',
  )
  if (contract) {
    genrePromise.value = String(contract.payload.genre_promise ?? '')
    backgroundPolicy.value = String(contract.payload.background_policy ?? '')
    culturalDistance.value = String(contract.payload.cultural_distance ?? '')
    protectedElements.value = Array.isArray(contract.payload.protected_elements)
      ? contract.payload.protected_elements.join('\n')
      : ''
    allowedChanges.value = Array.isArray(contract.payload.allowed_changes)
      ? contract.payload.allowed_changes.join('\n')
      : ''
    prohibitedChanges.value = Array.isArray(contract.payload.prohibited_changes)
      ? contract.payload.prohibited_changes.join('\n')
      : ''
  }
  if (!stageInitialized.value) {
    const requestedStage = Number(
      new URLSearchParams(window.location.search).get('recreationStage'),
    )
    activeStage.value =
      requestedStage >= 1 && requestedStage <= 6
        ? requestedStage
        : adoptedScalePlan.value
          ? 6
          : adoptedPilot.value
            ? 5
            : adoptedStrategy.value
              ? 4
              : targetContract.value
                ? 3
                : sourceModel.value
                  ? 2
                  : 1
    if (!(requestedStage >= 1 && requestedStage <= 6)) {
      await router.replace({
        path: route.path,
        query: {
          ...route.query,
          recreationStage: String(activeStage.value),
        },
      })
    }
    stageInitialized.value = true
  }
  if (
    !selectedPackageKey.value ||
    !workPackages.value.some(
      (item) => String(item.order) === selectedPackageKey.value,
    )
  ) {
    selectedPackageKey.value = String(workPackages.value[0]?.order ?? '')
  }
}

function selectStage(stage: number) {
  void router.replace({
    path: route.path,
    query: { ...route.query, recreationStage: String(stage) },
  })
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function openExportDialog() {
  exportSelection.value = exportRows.value
    .filter((item) => item.selectable)
    .map((item) => item.key)
  exportOpen.value = true
}

function toggleExportUnit(key: string) {
  exportSelection.value = exportSelection.value.includes(key)
    ? exportSelection.value.filter((item) => item !== key)
    : [...exportSelection.value, key]
}

async function run(label: string, action: () => Promise<unknown>) {
  running.value = label
  error.value = ''
  try {
    await action()
    await load()
  } catch (reason) {
    error.value = reason instanceof ApiError ? reason.message : '本轮协作没有完成，请保留当前输入后重试。'
  } finally {
    running.value = ''
  }
}

async function waitForRecreationRun(runId: string) {
  const deadline = Date.now() + 10 * 60 * 1000
  while (Date.now() < deadline) {
    const result = await api<RecreationRun>(
      `/cross-cultural-recreations/by-project/${props.projectId}/runs/${runId}`,
    )
    if (result.status === 'succeeded') return
    if (result.status === 'failed' || result.status === 'cancelled') {
      throw new Error(result.error_code || '本轮归化创作未完成')
    }
    await new Promise((resolve) => window.setTimeout(resolve, 500))
  }
  throw new Error('本轮归化创作仍在后台运行，请稍后刷新查看')
}

function analyzeSource() {
  return run('源作品分析', async () => {
    const result = await api<RecreationRun>(
      `/cross-cultural-recreations/by-project/${props.projectId}/analyze-source?background=true`,
      {
        method: 'POST',
        body: JSON.stringify({
          idempotency_key: crypto.randomUUID(),
          feedback: feedback.value || null,
        }),
      },
    )
    await waitForRecreationRun(result.run_id)
  })
}

function saveTargetContract() {
  return run('目标契约确认', () =>
    api(`/cross-cultural-recreations/by-project/${props.projectId}/target-contract`, {
      method: 'POST',
      body: JSON.stringify({
        genre_promise: genrePromise.value,
        background_policy: backgroundPolicy.value,
        cultural_distance: culturalDistance.value,
        protected_elements: lines(protectedElements.value),
        allowed_changes: lines(allowedChanges.value),
        prohibited_changes: lines(prohibitedChanges.value),
        idempotency_key: crypto.randomUUID(),
      }),
    }),
  )
}

function generateStrategies() {
  return run('归化策略生成', async () => {
    const result = await api<RecreationRun>(
      `/cross-cultural-recreations/by-project/${props.projectId}/strategies?background=true`,
      {
        method: 'POST',
        body: JSON.stringify({
          idempotency_key: crypto.randomUUID(),
          feedback: feedback.value || null,
        }),
      },
    )
    await waitForRecreationRun(result.run_id)
  })
}

function adopt(artifactId: string) {
  return run('候选采纳', () =>
    api(
      `/cross-cultural-recreations/by-project/${props.projectId}/artifacts/${artifactId}/adopt`,
      { method: 'POST' },
    ),
  )
}

function generatePilot() {
  return run('代表性试写', async () => {
    const result = await api<RecreationRun>(
      `/cross-cultural-recreations/by-project/${props.projectId}/pilots?background=true`,
      {
        method: 'POST',
        body: JSON.stringify({
          idempotency_key: crypto.randomUUID(),
          feedback: feedback.value || null,
        }),
      },
    )
    await waitForRecreationRun(result.run_id)
  })
}

function generateScalePlan() {
  return run('整书扩展规划', async () => {
    const result = await api<RecreationRun>(
      `/cross-cultural-recreations/by-project/${props.projectId}/scale-plans?background=true`,
      {
        method: 'POST',
        body: JSON.stringify({
          idempotency_key: crypto.randomUUID(),
          feedback: feedback.value || null,
        }),
      },
    )
    await waitForRecreationRun(result.run_id)
  })
}

function generateProductionUnit(workPackageKey: string) {
  return run(`工作包 ${workPackageKey} 再创作`, async () => {
    const result = await api<RecreationRun>(
      `/cross-cultural-recreations/by-project/${props.projectId}/work-packages/${encodeURIComponent(workPackageKey)}/drafts?background=true`,
      {
        method: 'POST',
        body: JSON.stringify({
          idempotency_key: crypto.randomUUID(),
          feedback: feedback.value || null,
        }),
      },
    )
    await waitForRecreationRun(result.run_id)
  })
}

function adoptProductionUnit(unitId: string) {
  return run('章节候选确认', () =>
    api(
      `/cross-cultural-recreations/by-project/${props.projectId}/production-units/${unitId}/adopt`,
      { method: 'POST' },
    ),
  )
}

function reviewProductionUnit(unitId: string) {
  return run('章节质量审读', () =>
    api(
      `/cross-cultural-recreations/by-project/${props.projectId}/production-units/${unitId}/review`,
      { method: 'POST' },
    ),
  )
}

function beginRevision(unit: ProductionUnit) {
  editingUnitId.value = unit.id
  editTitle.value = String(unit.payload.title ?? '')
  editDraft.value = String(unit.payload.target_language_draft ?? '')
}

function cancelRevision() {
  editingUnitId.value = ''
  editTitle.value = ''
  editDraft.value = ''
}

async function saveRevision(unitId: string) {
  await run('保存人工修订版本', () =>
    api(
      `/cross-cultural-recreations/by-project/${props.projectId}/production-units/${unitId}/revisions`,
      {
        method: 'POST',
        body: JSON.stringify({
          title: editTitle.value,
          target_language_draft: editDraft.value,
          idempotency_key: crypto.randomUUID(),
        }),
      },
    ),
  )
  cancelRevision()
}

function pipelineLabel(status: ProductionUnit['pipeline_status']) {
  return {
    drafting: '生成中',
    validating: '结构校验中',
    review_pending: '待审读',
    revision_required: '需修订',
    ready_for_decision: '待作者决定',
    adopted: '已采纳',
    failed: '生成失败',
  }[status]
}

function rationaleText(value: unknown) {
  if (!Array.isArray(value)) return String(value ?? '')
  return value
    .map((item) => {
      if (!item || typeof item !== 'object') return String(item)
      const record = item as Record<string, unknown>
      return [record.source_function, record.target_realization, record.reader_effect]
        .filter(Boolean)
        .join(' → ')
    })
    .filter(Boolean)
    .join('\n')
}

async function downloadManuscript() {
  running.value = '目标语稿合并'
  error.value = ''
  try {
    const query = new URLSearchParams()
    exportSelection.value.forEach((key) => query.append('work_package_keys', key))
    const manuscript = await api<{
      target_language: string
      content: string
    }>(
      `/cross-cultural-recreations/by-project/${props.projectId}/manuscript?${query.toString()}`,
    )
    const blob = new Blob([manuscript.content], {
      type: 'text/plain;charset=utf-8',
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `recreated-manuscript-${manuscript.target_language}.txt`
    link.click()
    URL.revokeObjectURL(url)
    exportOpen.value = false
  } catch (reason) {
    error.value =
      reason instanceof ApiError
        ? reason.message
        : '目标语稿合并没有完成，请保留已确认版本后重试。'
  } finally {
    running.value = ''
  }
}

watch(
  () => route.query.recreationStage,
  (value) => {
    const requestedStage = Number(value)
    if (requestedStage >= 1 && requestedStage <= 6) {
      activeStage.value = requestedStage
    }
  },
)

onMounted(async () => {
  window.addEventListener('scriptnow:recreation-export', openExportDialog)
  try {
    await load()
    if (!protectedElements.value) {
      protectedElements.value = props.direction.protected_elements || ''
    }
  } catch (reason) {
    error.value = reason instanceof ApiError ? reason.message : '项目状态读取失败'
  } finally {
    loading.value = false
  }
})
onUnmounted(() => {
  window.removeEventListener('scriptnow:recreation-export', openExportDialog)
})
</script>

<template>
  <section class="recreation-studio">
    <header class="recreation-hero">
      <div>
        <p class="eyebrow">故事归化 · 跨文化故事再创作</p>
        <h1>保留故事为什么动人，重建它如何在另一种文化中成立。</h1>
        <p>不逐句对应原文。创作团队先识别叙事功能，再重建人物动机、社会因果、类型承诺与目标语言声音。</p>
      </div>
      <div v-if="state" class="recreation-route">
        <span>{{ state.source_language }}</span><b>→</b><span>{{ state.target_language }}</span>
        <small>{{ state.target_market }} · {{ state.distribution_context }}</small>
      </div>
    </header>

    <div v-if="loading" class="recreation-empty">正在读取归化项目…</div>
    <template v-else-if="state">
      <ol class="recreation-progress" aria-label="归化工作区">
        <li :class="{ done: sourceModel, active: activeStage === 1 }">
          <button :aria-current="activeStage === 1 ? 'step' : undefined" @click="selectStage(1)"><span>01</span>读懂原作</button>
        </li>
        <li :class="{ done: targetContract, active: activeStage === 2 }">
          <button :aria-current="activeStage === 2 ? 'step' : undefined" @click="selectStage(2)"><span>02</span>确认目标</button>
        </li>
        <li :class="{ done: adoptedStrategy, active: activeStage === 3 }">
          <button :aria-current="activeStage === 3 ? 'step' : undefined" @click="selectStage(3)"><span>03</span>选择策略</button>
        </li>
        <li :class="{ done: adoptedPilot, active: activeStage === 4 }">
          <button :aria-current="activeStage === 4 ? 'step' : undefined" @click="selectStage(4)"><span>04</span>试写验证</button>
        </li>
        <li :class="{ done: adoptedScalePlan, active: activeStage === 5 }">
          <button :aria-current="activeStage === 5 ? 'step' : undefined" @click="selectStage(5)"><span>05</span>整书蓝图</button>
        </li>
        <li :class="{ done: productionComplete, active: activeStage === 6 }">
          <button :aria-current="activeStage === 6 ? 'step' : undefined" @click="selectStage(6)"><span>06</span>逐章生产</button>
        </li>
      </ol>

      <p v-if="error" class="form-error recreation-error">{{ error }}</p>
      <p v-if="running" class="recreation-running">创作团队正在进行“{{ running }}”，当前页面会保留已有版本。</p>

      <section v-show="activeStage === 1" class="recreation-stage">
        <div class="stage-heading">
          <div><p class="eyebrow">01 · 源故事模型</p><h2>先判断哪些是故事基因，哪些只是文化载体。</h2></div>
          <button class="primary" :disabled="Boolean(running)" @click="analyzeSource">
            {{ sourceModel ? '重新分析并形成新版本' : '分析源作品' }}
          </button>
        </div>
        <div v-if="sourceModel" class="source-model-grid">
          <article>
            <h3>故事为何成立</h3>
            <p>{{ sourceModel.payload.story_summary }}</p>
          </article>
          <article>
            <h3>故事基因</h3>
            <ul><li v-for="(item, index) in sourceModel.payload.story_genes" :key="index"><strong>{{ item.name }}</strong><span>{{ item.narrative_function }}</span></li></ul>
          </article>
          <article>
            <h3>跨文化理解门槛</h3>
            <ul><li v-for="(item, index) in sourceModel.payload.cultural_gaps" :key="index"><strong>{{ item.source_element }}</strong><span>{{ item.reader_failure_risk }}</span></li></ul>
          </article>
          <article>
            <h3>保护与待确认</h3>
            <p>{{ sourceModel.payload.protected_elements?.join('；') }}</p>
            <small>{{ sourceModel.payload.uncertainties?.join('；') }}</small>
          </article>
        </div>
        <p v-else class="recreation-empty">分析会形成可追溯的源故事模型，不会直接开始改写。</p>
      </section>

      <section v-show="activeStage === 2" class="recreation-stage" :class="{ locked: !sourceModel }">
        <div class="stage-heading">
          <div><p class="eyebrow">02 · 目标故事契约</p><h2>明确面向谁创作，以及什么绝不能被静默改变。</h2></div>
          <button class="primary" :disabled="!sourceModel || Boolean(running) || !genrePromise || !backgroundPolicy || !culturalDistance || !protectedElements" @click="saveTargetContract">
            {{ targetContract ? '保存为新契约版本' : '确认目标契约' }}
          </button>
        </div>
        <div class="target-contract-form">
          <label>目标类型与阅读承诺<textarea v-model="genrePromise" rows="3" placeholder="目标读者期待怎样的关系、冲突、节奏与情绪兑现" /></label>
          <label>背景处理原则<textarea v-model="backgroundPolicy" rows="3" placeholder="保留中国背景、跨文化背景或迁移背景；说明判断原则" /></label>
          <label>文化距离策略<textarea v-model="culturalDistance" rows="3" placeholder="哪些文化经验保留，哪些需要解释、迁移或重构" /></label>
          <label>必须保护的内容<textarea v-model="protectedElements" rows="4" placeholder="每行一项" /></label>
          <label>允许改变<textarea v-model="allowedChanges" rows="3" placeholder="每行一项" /></label>
          <label>禁止改变<textarea v-model="prohibitedChanges" rows="3" placeholder="每行一项" /></label>
        </div>
      </section>

      <section v-show="activeStage === 3" class="recreation-stage" :class="{ locked: !targetContract }">
        <div class="stage-heading">
          <div><p class="eyebrow">03 · 归化策略</p><h2>比较三种不同的跨文化叙事解法。</h2></div>
          <button class="primary" :disabled="!targetContract || Boolean(running)" @click="generateStrategies">
            {{ strategies.length ? '根据反馈生成新版候选' : '生成三套策略' }}
          </button>
        </div>
        <div v-if="strategies.length" class="strategy-grid">
          <article v-for="strategy in strategies" :key="strategy.id" :class="{ adopted: strategy.status === 'adopted' }">
            <p class="eyebrow">方向 {{ strategy.ordinal }} · v{{ strategy.version }}</p>
            <h3>{{ strategy.payload.title }}</h3>
            <p>{{ strategy.payload.target_premise }}</p>
            <h4>再创作主张</h4><p>{{ strategy.payload.recreation_thesis }}</p>
            <h4>关键迁移</h4>
            <ul><li v-for="(decision, index) in strategy.payload.localization_decisions" :key="index">{{ decision.source_function }} → {{ decision.target_carrier }}</li></ul>
            <h4>风险</h4><p>{{ strategy.payload.risks?.join('；') }}</p>
            <button v-if="strategy.status !== 'adopted'" class="primary" :disabled="Boolean(running)" @click="adopt(strategy.id)">采用此策略</button>
            <span v-else class="adopted-badge">已采用</span>
          </article>
        </div>
        <p v-else class="recreation-empty">策略不是“换人名地名”，而是对叙事功能在目标文化中的承载方式作出完整解释。</p>
      </section>

      <section v-show="activeStage === 4" class="recreation-stage" :class="{ locked: !adoptedStrategy }">
        <div class="stage-heading">
          <div><p class="eyebrow">04 · 试写实验室</p><h2>先验证代表性单元，再决定是否扩展整部作品。</h2></div>
          <button class="primary" :disabled="!adoptedStrategy || Boolean(running)" @click="generatePilot">
            {{ pilots.length ? '根据反馈重新试写' : '生成代表性试写' }}
          </button>
        </div>
        <article v-for="pilot in pilots" :key="pilot.id" class="pilot-card">
          <header><div><p class="eyebrow">试写候选 · v{{ pilot.version }}</p><h3>{{ pilot.payload.unit_title }}</h3></div><button v-if="pilot.status !== 'adopted'" class="secondary" @click="adopt(pilot.id)">确认试写</button><span v-else class="adopted-badge">试写已确认</span></header>
          <p class="pilot-rationale">{{ pilot.payload.rationale }}</p>
          <div class="pilot-manuscript">{{ pilot.payload.target_language_draft }}</div>
          <details><summary>查看改编依据与故事基因追踪</summary><pre>{{ JSON.stringify({ change_notes: pilot.payload.change_notes, gene_trace: pilot.payload.gene_trace, open_questions: pilot.payload.open_questions }, null, 2) }}</pre></details>
        </article>
        <p v-if="!pilots.length" class="recreation-empty">试写将同时显示目标语正文、关键改编理由和故事基因追踪。</p>
      </section>

      <section v-show="activeStage === 5" class="recreation-stage" :class="{ locked: !adoptedPilot }">
        <div class="stage-heading">
          <div>
            <p class="eyebrow">05 · 整书扩展方案</p>
            <h2>把已验证方向转化为可执行、可追踪的整书生产蓝图。</h2>
          </div>
          <button
            class="primary"
            :disabled="!adoptedPilot || Boolean(running)"
            @click="generateScalePlan"
          >
            {{ scalePlans.length ? '根据反馈重建扩展方案' : '生成整书扩展方案' }}
          </button>
        </div>
        <article
          v-for="plan in scalePlans"
          :key="plan.id"
          class="scale-plan-card"
          :class="{ adopted: plan.status === 'adopted' }"
        >
          <header>
            <div>
              <p class="eyebrow">生产蓝图 · v{{ plan.version }}</p>
              <h3>{{ plan.payload.work_packages?.length ?? 0 }} 个再创作工作包</h3>
            </div>
            <button
              v-if="plan.status !== 'adopted'"
              class="secondary"
              :disabled="Boolean(running)"
              @click="adopt(plan.id)"
            >
              确认整书方案
            </button>
            <span v-else class="adopted-badge">整书方案已确认</span>
          </header>
          <div class="scale-plan-summary">
            <section>
              <h4>目标故事圣经</h4>
              <dl>
                <template
                  v-for="(value, key) in plan.payload.target_story_bible"
                  :key="String(key)"
                >
                  <dt>{{ key }}</dt>
                  <dd>{{ Array.isArray(value) ? value.join('；') : value }}</dd>
                </template>
              </dl>
            </section>
            <section>
              <h4>连续性约束</h4>
              <ul>
                <li v-for="rule in plan.payload.continuity_rules" :key="rule">
                  {{ rule }}
                </li>
              </ul>
            </section>
          </div>
          <details open>
            <summary>查看整书工作包</summary>
            <ol class="work-package-list">
              <li
                v-for="(workPackage, index) in plan.payload.work_packages"
                :key="`${workPackage.order}-${index}`"
              >
                <span>{{ workPackage.order }}</span>
                <div>
                  <h4 data-i18n-skip>{{ workPackage.title }}</h4>
                  <p data-i18n-skip>{{ workPackage.narrative_function }}</p>
                  <small data-i18n-skip>{{ workPackage.target_design }}</small>
                </div>
              </li>
            </ol>
          </details>
          <details>
            <summary>查看人物迁移、质量门禁与未决问题</summary>
            <pre>{{ JSON.stringify({
              character_migrations: plan.payload.character_migrations,
              quality_gates: plan.payload.quality_gates,
              unresolved_decisions: plan.payload.unresolved_decisions,
            }, null, 2) }}</pre>
          </details>
        </article>
        <p v-if="!scalePlans.length" class="recreation-empty">
          只有确认过的试写才能进入整书扩展；章节与工作包数量由源作品结构和目标契约共同决定。
        </p>
      </section>

      <section v-show="activeStage === 6" class="recreation-stage chapter-pipeline-stage" :class="{ locked: !adoptedScalePlan }">
        <div class="stage-heading">
          <div>
            <p class="eyebrow">06 · 章节生产管线</p>
            <h2>一章一条可恢复管线：生成、审读、人工修订，最后由作者决定。</h2>
          </div>
          <div v-if="productionComplete" class="production-complete-actions">
            <span class="adopted-badge">全部章节已确认</span>
            <button class="primary" :disabled="Boolean(running)" @click="downloadManuscript">
              下载目标语合稿
            </button>
          </div>
        </div>
        <div v-if="adoptedScalePlan" class="chapter-pipeline">
          <aside class="chapter-pipeline-nav" aria-label="章节列表">
            <button
              v-for="(workPackage, index) in workPackages"
              :key="`${workPackage.order}-${index}`"
              :class="{
                active: String(workPackage.order) === String(selectedWorkPackage?.order),
                adopted: adoptedProductionKeys.has(String(workPackage.order)),
              }"
              @click="selectedPackageKey = String(workPackage.order)"
            >
              <span>{{ workPackage.chapter_number ?? index + 1 }}</span>
              <strong data-i18n-skip>{{ workPackage.title }}</strong>
              <small>
                {{
                  productionUnitsFor(String(workPackage.order)).length
                    ? pipelineLabel(
                        [...productionUnitsFor(String(workPackage.order))]
                          .sort((a, b) => b.version - a.version)[0].pipeline_status,
                      )
                    : '尚未开始'
                }}
              </small>
            </button>
          </aside>

          <main v-if="selectedWorkPackage" class="chapter-pipeline-main">
            <header class="chapter-pipeline-heading">
              <div>
                <p class="eyebrow">
                  第 {{ selectedWorkPackage.chapter_number ?? workPackages.indexOf(selectedWorkPackage) + 1 }} 章
                  · {{ selectedWorkPackage.order }}
                </p>
                <h3 data-i18n-skip>{{ selectedWorkPackage.title }}</h3>
                <p data-i18n-skip>{{ selectedWorkPackage.narrative_function }}</p>
              </div>
              <button
                class="primary"
                :disabled="Boolean(running)"
                @click="generateProductionUnit(String(selectedWorkPackage.order))"
              >
                {{ selectedUnits.length ? '根据反馈生成新版' : '生成章节候选稿' }}
              </button>
            </header>
            <p class="production-design" data-i18n-skip>{{ selectedWorkPackage.target_design }}</p>

            <section v-if="selectedUnit" class="production-unit chapter-candidate">
              <header>
                <div>
                  <p class="eyebrow">
                    候选稿 · v{{ selectedUnit.version }}
                    · {{ selectedUnit.revision_kind === 'manual' ? '人工修订' : 'Agent 初稿' }}
                  </p>
                  <h4>{{ selectedUnit.payload.title || selectedWorkPackage.title }}</h4>
                </div>
                <span class="pipeline-status" :data-status="selectedUnit.pipeline_status">
                  {{ pipelineLabel(selectedUnit.pipeline_status) }}
                </span>
              </header>

              <template v-if="editingUnitId === selectedUnit.id">
                <label class="chapter-editor-title">
                  章节标题
                  <input v-model="editTitle" />
                </label>
                <label class="chapter-editor-body">
                  候选正文
                  <textarea v-model="editDraft" rows="28" />
                </label>
                <div class="chapter-editor-actions">
                  <button class="secondary" @click="cancelRevision">取消</button>
                  <button
                    class="primary"
                    :disabled="Boolean(running) || !editTitle.trim() || !editDraft.trim()"
                    @click="saveRevision(selectedUnit.id)"
                  >
                    另存人工修订版本
                  </button>
                </div>
              </template>
              <template v-else-if="selectedUnit.pipeline_status === 'drafting' || selectedUnit.pipeline_status === 'validating'">
                <div class="chapter-generation-state">
                  <span class="pipeline-spinner" />
                  <div><strong>主笔正在生成本章</strong><p>生成期间只读；结构校验完成后才能审读与修订。</p></div>
                </div>
              </template>
              <template v-else-if="selectedUnit.pipeline_status === 'failed'">
                <div class="chapter-failure">
                  <strong>本章生成未完成</strong>
                  <p>{{ selectedUnit.failure_reason }}</p>
                  <button class="secondary" @click="generateProductionUnit(String(selectedWorkPackage.order))">重新生成</button>
                </div>
              </template>
              <template v-else>
                <p class="production-rationale" data-i18n-skip>{{ rationaleText(selectedUnit.payload.recreation_rationale) }}</p>
                <article class="production-manuscript" data-i18n-skip>{{ selectedUnit.payload.target_language_draft }}</article>
                <div v-if="selectedUnit.review_report" class="chapter-review-report">
                  <strong>{{ selectedUnit.review_report.verdict === 'pass' ? '审读通过' : '审读要求修订' }}</strong>
                  <ul v-if="selectedUnit.review_report.findings.length">
                    <li v-for="(finding, index) in selectedUnit.review_report.findings" :key="index" data-i18n-skip>{{ finding.message }}</li>
                  </ul>
                  <p v-else>结构化章节契约与质量自检均已通过，等待作者决定。</p>
                </div>
                <div class="chapter-decision-bar">
                  <button
                    class="secondary"
                    :disabled="Boolean(running)"
                    @click="beginRevision(selectedUnit)"
                  >
                    人工修订
                  </button>
                  <button
                    v-if="selectedUnit.pipeline_status === 'review_pending' || selectedUnit.pipeline_status === 'revision_required'"
                    class="secondary"
                    :disabled="Boolean(running)"
                    @click="reviewProductionUnit(selectedUnit.id)"
                  >
                    {{ selectedUnit.review_report ? '重新审读' : '开始质量审读' }}
                  </button>
                  <button
                    v-if="selectedUnit.pipeline_status === 'ready_for_decision'"
                    class="primary"
                    :disabled="Boolean(running)"
                    @click="adoptProductionUnit(selectedUnit.id)"
                  >
                    采纳为确认正文
                  </button>
                  <span v-if="selectedUnit.status === 'adopted'" class="adopted-badge">已成为确认正文</span>
                </div>
                <details>
                  <summary>查看上下文快照、故事基因与连续性</summary>
                  <pre>{{ JSON.stringify({
                    context_snapshot: selectedUnit.context_snapshot,
                    gene_trace: selectedUnit.payload.gene_trace,
                    continuity_updates: selectedUnit.payload.continuity_updates,
                    quality_self_check: selectedUnit.payload.quality_self_check,
                    open_questions: selectedUnit.payload.open_questions,
                  }, null, 2) }}</pre>
                </details>
              </template>
            </section>
            <p v-else class="recreation-empty">
              尚未生成本章候选稿。只有经审读并由作者采纳的版本，才会进入后续章节上下文。
            </p>
          </main>

          <aside v-if="selectedWorkPackage" class="chapter-pipeline-rail">
            <p class="eyebrow">章节契约</p>
            <dl>
              <dt>源素材范围</dt><dd data-i18n-skip>{{ selectedWorkPackage.source_scope }}</dd>
              <dt>前置依赖</dt><dd data-i18n-skip>{{ selectedWorkPackage.dependencies?.join('；') || '无' }}</dd>
              <dt>保护要素</dt><dd data-i18n-skip>{{ selectedWorkPackage.protected_genes?.join('；') || '按整书契约' }}</dd>
              <dt>目标篇幅</dt><dd>{{ selectedWorkPackage.target_words ? `${selectedWorkPackage.target_words} 词` : '遵循项目设置' }}</dd>
            </dl>
            <ol class="chapter-pipeline-steps">
              <li :class="{ done: selectedUnit }">生成候选</li>
              <li :class="{ done: selectedUnit?.review_report }">质量审读</li>
              <li :class="{ done: selectedUnit?.revision_kind === 'manual' }">人工修订（可选）</li>
              <li :class="{ done: selectedUnit?.status === 'adopted' }">作者采纳</li>
            </ol>
          </aside>
        </div>
        <p v-else class="recreation-empty">
          请先确认整书蓝图。章节数量、顺序与篇幅来自项目契约和已确认方案，不由界面写死。
        </p>
      </section>

      <section class="recreation-feedback">
        <label>给创作团队的反馈
          <textarea v-model="feedback" rows="3" placeholder="例如：保留原作家庭伦理压力，但不要把它简化成个人叛逆；目标读者为北美女性向移动网文读者。" />
        </label>
        <small>反馈会进入下一轮分析、策略或试写，不覆盖已经采纳的版本。</small>
      </section>
      <Teleport to="body">
        <div v-if="exportOpen" class="delivery-backdrop" @click.self="exportOpen = false">
          <section class="delivery-modal recreation-export-modal" role="dialog" aria-modal="true" aria-labelledby="recreation-export-title">
            <header>
              <div>
                <p class="eyebrow">Cross-cultural recreation delivery</p>
                <h2 id="recreation-export-title">选择要导出的归化章节</h2>
                <p>仅已由作者确认的章节可选；导出顺序遵循整书蓝图。</p>
              </div>
              <button type="button" aria-label="关闭" @click="exportOpen = false">×</button>
            </header>
            <div class="scope-tree recreation-export-scope">
              <article>
                <label
                  v-for="row in exportRows"
                  :key="row.key"
                  :class="{ disabled: !row.selectable }"
                >
                  <input
                    type="checkbox"
                    :checked="exportSelection.includes(row.key)"
                    :disabled="!row.selectable"
                    @change="toggleExportUnit(row.key)"
                  />
                  <span>第 {{ row.chapterNumber }} 章 · {{ row.title }}</span>
                  <em>{{ row.selectable ? `确认稿 v${row.version}` : '尚无确认稿' }}</em>
                </label>
              </article>
            </div>
            <footer>
              <span>已选 {{ exportSelection.length }} 章</span>
              <button
                class="primary"
                type="button"
                :disabled="Boolean(running) || !exportSelection.length"
                @click="downloadManuscript"
              >
                {{ running === '目标语稿合并' ? '正在导出…' : '导出所选章节' }}
              </button>
            </footer>
          </section>
        </div>
      </Teleport>
    </template>
  </section>
</template>
