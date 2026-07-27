<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useLocale } from '@scriptnow/shared'

import { api, ApiError } from '../api'
import AppShell from '../components/AppShell.vue'
import { useProjectsStore } from '../stores/projects'
import type { Medium, SourceMode } from '../types'

const step = ref(1)
const medium = ref<Medium | null>(null)
const workflowKind = ref<'original' | 'adaptation' | 'cross_cultural_recreation'>('original')
const sourceMode = ref<SourceMode | null>(null)
const name = ref('')
const selectedGenres = ref<string[]>([])
const customGenre = ref('')
const premise = ref('')
const tone = ref('')
const worldSetting = ref('')
const creativeLanguage = ref('')
const sourceFile = ref<File | null>(null)
const structure = ref('')
const customStructure = ref('')
const scriptFormat = ref<'chinese' | 'hollywood' | null>(null)
const volumeOne = ref<number | null>(null)
const volumeTwo = ref<number | null>(null)
const volumeThree = ref<number | null>(null)
const novelChapterTargetWords = ref<number | null>(null)
const submitting = ref(false)
const submissionError = ref('')
const translationSourceName = ref('')
const translationTarget = ref('ja-JP')
const translationTab = ref<'library' | 'upload'>('library')
const translationFile = ref<File | null>(null)
const recreationSourceLanguage = ref('zh-CN')
const recreationTargetLanguage = ref('en-US')
const recreationTargetMarket = ref('')
const recreationTargetAudience = ref('')
const selectedTargetMarkets = ref<string[]>([])
const selectedTargetAudiences = ref<string[]>([])
const recreationDistributionContext = ref('')
const recreationProtectedElements = ref('')
const targetMarketPresets = [
  '北美英语网络文学',
  '英国及爱尔兰英语市场',
  '日本网络小说／轻小说',
  '韩国网络文学',
  '东南亚英语移动网文',
  '中国大陆网络文学',
  '中国台湾及香港繁体市场',
  '全球英语电子书市场',
]
const targetAudiencePresets = [
  '女性向情感／言情读者',
  '男性向成长／升级读者',
  '青少年及青年读者',
  '成年悬疑／惊悚读者',
  '奇幻／超自然类型读者',
  '移动端短章节读者',
  '付费连载读者',
  '轻阅读大众读者',
]
type GenreOption = {
  key: string
  label_zh: string
  label_en: string
  skill_keys: string[]
}
type InspirationCandidate = {
  title: string
  premise: string
  tone: string
  world_setting: string
  genre_suggestions: string[]
  questions: string[]
  model_key: string
  skill_keys: string[]
}
const genreOptions = ref<GenreOption[]>([])
const genreOptionsLoading = ref(false)
const genreSearch = ref('')
const showAllGenres = ref(false)
const inspirationMode = ref(false)
const inspirationSeed = ref('')
const inspirationLoading = ref(false)
const inspirationError = ref('')
const inspirationCandidate = ref<InspirationCandidate | null>(null)
const projects = useProjectsStore()
const router = useRouter()
const { isEnglish } = useLocale()
const genrePresets = computed(() => genreOptions.value)
const visibleGenrePresets = computed(() => {
  const query = genreSearch.value.trim().toLocaleLowerCase()
  const matched = query
    ? genrePresets.value.filter((item) =>
        [item.key, item.label_zh, item.label_en].some((value) =>
          value.toLocaleLowerCase().includes(query),
        ),
      )
    : genrePresets.value
  if (query || showAllGenres.value) return matched
  const localized = matched.filter(
    (item) =>
      selectedGenres.value.includes(item.key) ||
      [...item.label_zh].some((char) => /[\p{Script=Han}]/u.test(char)),
  )
  return localized.slice(0, 30)
})
const genre = computed(() =>
  [...selectedGenres.value, ...customGenre.value.split(/[,，、/]/)]
    .map((item) => item.trim())
    .filter((item, index, items) => item && items.indexOf(item) === index)
    .join(', '),
)
const combinedTargetMarket = computed(() =>
  [...selectedTargetMarkets.value, recreationTargetMarket.value]
    .map((item) => item.trim())
    .filter((item, index, items) => item && items.indexOf(item) === index)
    .join('；'),
)
const combinedTargetAudience = computed(() =>
  [...selectedTargetAudiences.value, recreationTargetAudience.value]
    .map((item) => item.trim())
    .filter((item, index, items) => item && items.indexOf(item) === index)
    .join('；'),
)
const canContinue = computed(
  () => {
    if (step.value === 1) return medium.value !== null
    if (medium.value === 'translation') return true  // skip to submit
    if (workflowKind.value === 'cross_cultural_recreation') {
      if (step.value === 2) return Boolean(name.value.trim() && sourceFile.value)
      if (step.value === 3) {
        return Boolean(
          recreationSourceLanguage.value &&
            recreationTargetLanguage.value &&
            combinedTargetMarket.value &&
            combinedTargetAudience.value,
        )
      }
      return true
    }
    if (step.value === 2) return sourceMode.value !== null
    if (step.value === 3) {
      return Boolean(
      name.value.trim() &&
        premise.value.trim() &&
        creativeLanguage.value &&
        structure.value &&
        (structure.value !== 'custom' || customStructure.value.trim()) &&
        volumeOne.value !== null &&
        volumeOne.value > 0 &&
        volumeTwo.value !== null &&
        volumeTwo.value > 0 &&
        (medium.value !== 'script' ||
          (scriptFormat.value !== null &&
            volumeThree.value !== null &&
            volumeThree.value > 0)) &&
        (medium.value !== 'novel' ||
          (novelChapterTargetWords.value !== null && novelChapterTargetWords.value > 0)) &&
        (sourceMode.value === 'original' || sourceFile.value),
      )
    }
    return true
  },
)

function toggleGenre(value: string) {
  selectedGenres.value = selectedGenres.value.includes(value)
    ? selectedGenres.value.filter((item) => item !== value)
    : [...selectedGenres.value, value]
}

function togglePreset(values: string[], value: string) {
  return values.includes(value)
    ? values.filter((item) => item !== value)
    : [...values, value]
}

watch(medium, async (value) => {
  genreOptions.value = []
  selectedGenres.value = []
  if (value !== 'novel' && value !== 'script') return
  genreOptionsLoading.value = true
  try {
    const response = await api<{ genres: GenreOption[] }>(`/creative-options/${value}`)
    genreOptions.value = response.genres
    showAllGenres.value = false
    genreSearch.value = ''
  } finally {
    genreOptionsLoading.value = false
  }
})

watch(recreationTargetLanguage, (language) => {
  if (selectedTargetMarkets.value.length || recreationTargetMarket.value.trim()) return
  const recommendedMarket: Record<string, string> = {
    'en-US': '北美英语网络文学',
    'en-GB': '英国及爱尔兰英语市场',
    'ja-JP': '日本网络小说／轻小说',
    'ko-KR': '韩国网络文学',
    'zh-CN': '中国大陆网络文学',
    'zh-TW': '中国台湾及香港繁体市场',
  }
  const recommendation = recommendedMarket[language]
  if (recommendation) selectedTargetMarkets.value = [recommendation]
}, { immediate: true })

async function generateInspiration() {
  if (
    (medium.value !== 'novel' && medium.value !== 'script') ||
    inspirationSeed.value.trim().length < 2
  ) return
  inspirationLoading.value = true
  inspirationError.value = ''
  inspirationCandidate.value = null
  try {
    inspirationCandidate.value = await api<InspirationCandidate>('/creative-inspiration', {
      method: 'POST',
      body: JSON.stringify({
        medium: medium.value,
        seed: inspirationSeed.value.trim(),
        language: creativeLanguage.value || 'zh-CN',
        genres: selectedGenres.value,
      }),
    })
  } catch (error) {
    inspirationError.value =
      error instanceof ApiError && error.status === 502
        ? isEnglish.value
          ? 'No complete direction was generated this time. Your idea is still here—please try again.'
          : '这次没有生成完整的创作方向。你的想法仍在，可以重新生成。'
        : isEnglish.value
          ? 'Inspiration generation was interrupted. Please try again.'
          : '灵感生成暂时中断，请重试。'
  } finally {
    inspirationLoading.value = false
  }
}

function applyInspiration() {
  const candidate = inspirationCandidate.value
  if (!candidate) return
  if (!name.value.trim()) name.value = candidate.title
  premise.value = candidate.premise
  tone.value = candidate.tone
  worldSetting.value = candidate.world_setting
  const available = new Set(genreOptions.value.map((item) => item.key))
  selectedGenres.value = [
    ...new Set([
      ...selectedGenres.value,
      ...candidate.genre_suggestions.filter((item) => available.has(item)),
    ]),
  ]
  inspirationMode.value = false
}

function creationErrorMessage(error: unknown, recreation = false) {
  if (error instanceof ApiError) return error.message
  if (isEnglish.value) {
    return recreation
      ? 'The recreation project could not be created. Please try again.'
      : 'The project could not be created. Please try again.'
  }
  return recreation ? '归化项目创建未完成，请重试。' : '项目创建未完成，请重试。'
}

async function finish() {
  submissionError.value = ''
  if (medium.value === 'translation') {
    submitting.value = true
    try {
      if (translationTab.value === 'upload' && translationFile.value) {
        const form = new FormData()
        form.append('file', translationFile.value)
        form.append('target_language', translationTarget.value)
        const resp = await fetch('/api/translation/documents', { method: 'POST', body: form })
        if (!resp.ok) throw new Error(`upload failed: ${resp.status}`)
        const data = await resp.json()
        return router.push(`/projects/${data.project_id}`)
      }
      const resp = await fetch('/api/translation/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_project_id: (projects.items.find(p => p.name === translationSourceName.value) || {} as any).id || '',
          target_language: translationTarget.value,
          translation_mode: 'faithful',
        }),
      })
      if (!resp.ok) throw new Error('translation creation failed')
      const data = await resp.json()
      return router.push(`/projects/${data.id}`)
    } catch (error) {
      submissionError.value = creationErrorMessage(error)
    } finally {
      submitting.value = false
    }
    return
  }
  if (workflowKind.value === 'cross_cultural_recreation') {
    if (!sourceFile.value) return
    submitting.value = true
    try {
      const project = await projects.create({
        name: name.value.trim(),
        medium: 'novel',
        sourceMode: 'adaptation',
        workflowKind: 'cross_cultural_recreation',
        direction: {
          language: recreationTargetLanguage.value,
          source_language: recreationSourceLanguage.value,
          target_language: recreationTargetLanguage.value,
          target_market: combinedTargetMarket.value,
          target_audience: combinedTargetAudience.value,
          distribution_context: recreationDistributionContext.value.trim(),
          protected_elements: recreationProtectedElements.value.trim(),
        },
      })
      await projects.upload(project.id, sourceFile.value)
      await api('/cross-cultural-recreations', {
        method: 'POST',
        body: JSON.stringify({
          project_id: project.id,
          source_language: recreationSourceLanguage.value,
          target_language: recreationTargetLanguage.value,
          target_market: combinedTargetMarket.value,
          target_audience: combinedTargetAudience.value,
          distribution_context: recreationDistributionContext.value.trim(),
        }),
      })
      return router.push(`/projects/${project.id}`)
    } catch (error) {
      submissionError.value = creationErrorMessage(error, true)
    } finally {
      submitting.value = false
    }
    return
  }
  if (
    !medium.value ||
    !sourceMode.value ||
    !structure.value ||
    volumeOne.value === null ||
    volumeTwo.value === null
  ) return
  submitting.value = true
  try {
    const project = await projects.create({
      name: name.value.trim(),
      medium: medium.value,
      sourceMode: sourceMode.value,
      workflowKind: workflowKind.value,
      direction: {
        genre: genre.value,
        premise: premise.value,
        tone: tone.value,
        world_setting: worldSetting.value,
        language: creativeLanguage.value,
        structure:
          structure.value === 'custom' ? customStructure.value.trim() : structure.value,
        script_format: medium.value === 'script' ? scriptFormat.value ?? '' : '',
        volume_one: String(volumeOne.value),
        volume_two: String(volumeTwo.value),
        volume_three: medium.value === 'script' ? String(volumeThree.value ?? '') : '',
        chapter_target_words:
          medium.value === 'novel' ? String(novelChapterTargetWords.value ?? '') : '',
      },
    })
    if (sourceMode.value === 'adaptation' && sourceFile.value) {
      await projects.upload(project.id, sourceFile.value)
    }
    await router.push(`/projects/${project.id}`)
  } catch (error) {
    submissionError.value = creationErrorMessage(error)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <AppShell title="种下新故事" eyebrow="四步创作向导">
    <ol class="stepper" aria-label="创建进度">
      <li v-for="item in 4" :key="item" :class="{ active: step === item, done: step > item }"><span>{{ item }}</span></li>
    </ol>
    <section class="wizard-card">
      <div v-if="step === 1">
        <p class="eyebrow">01 · 作品形态</p><h2>这次要生长成什么？</h2>
        <div class="choice-grid">
          <button v-for="item in ([['script','剧本','以场景、动作和对白推进'],['novel','小说','以章节、叙述和内心推进'],['translation','翻译','忠实转换文学作品到目标语言']] as const)" :key="item[0]" class="choice-card" :class="{ selected: medium === item[0] && workflowKind !== 'cross_cultural_recreation' }" @click="medium = item[0]; workflowKind = item[0] === 'translation' ? 'adaptation' : 'original'">
            <strong>{{ item[1] }}</strong><span>{{ item[2] }}</span>
          </button>
          <button
            class="choice-card recreation-choice"
            :class="{ selected: workflowKind === 'cross_cultural_recreation' }"
            @click="medium = 'novel'; workflowKind = 'cross_cultural_recreation'"
          >
            <strong>故事归化</strong>
            <span>保留故事基因，为目标文化重新建立人物、因果与阅读体验</span>
          </button>
        </div>
      </div>
      <div v-else-if="step === 2 && workflowKind === 'cross_cultural_recreation'" class="form-stack">
        <p class="eyebrow">02 · 源作品</p>
        <h2>先让创作团队读懂原作为什么成立。</h2>
        <p class="muted">这里不做逐句翻译。系统将提取故事基因、文化脚本、社会因果和需要作者确认的改编边界。</p>
        <label>项目名称
          <input v-model="name" maxlength="200" placeholder="为本次归化项目命名" />
        </label>
        <label>上传源作品
          <input type="file" accept=".txt,.pdf,.docx" required @change="sourceFile = ($event.target as HTMLInputElement).files?.[0] ?? null" />
          <small class="muted">支持 TXT、PDF、DOCX；原文只作为可追溯创作依据，不要求译文逐句对应。</small>
        </label>
      </div>
      <div v-else-if="step === 3 && workflowKind === 'cross_cultural_recreation'" class="form-stack">
        <p class="eyebrow">03 · 目标故事契约</p>
        <h2>不是“欧美化”，而是明确写给谁、在哪里读。</h2>
        <div class="choice-grid compact-choice-grid">
          <label>源作品语言
            <select v-model="recreationSourceLanguage">
              <option value="zh-CN">简体中文</option><option value="zh-TW">繁體中文</option>
              <option value="en-US">English</option><option value="ja-JP">日本語</option><option value="ko-KR">한국어</option>
            </select>
          </label>
          <label>目标创作语言
            <select v-model="recreationTargetLanguage">
              <option value="en-US">English (US)</option><option value="en-GB">English (UK)</option>
              <option value="ja-JP">日本語</option><option value="ko-KR">한국어</option>
              <option value="zh-CN">简体中文</option><option value="zh-TW">繁體中文</option>
            </select>
          </label>
        </div>
        <fieldset class="contract-preset-picker">
          <legend>目标市场</legend>
          <p class="muted">可多选主流市场，并在下方补充更具体的平台或地区。</p>
          <div class="contract-preset-list">
            <button
              v-for="item in targetMarketPresets"
              :key="item"
              type="button"
              :class="{ selected: selectedTargetMarkets.includes(item) }"
              @click="selectedTargetMarkets = togglePreset(selectedTargetMarkets, item)"
            >
              {{ item }}
            </button>
          </div>
          <label>补充市场
            <input v-model="recreationTargetMarket" placeholder="例如：Wattpad 北美女性向付费连载" />
          </label>
        </fieldset>
        <fieldset class="contract-preset-picker">
          <legend>目标读者</legend>
          <p class="muted">选择主要读者画像；年龄、分级和特殊偏好可继续补充。</p>
          <div class="contract-preset-list">
            <button
              v-for="item in targetAudiencePresets"
              :key="item"
              type="button"
              :class="{ selected: selectedTargetAudiences.includes(item) }"
              @click="selectedTargetAudiences = togglePreset(selectedTargetAudiences, item)"
            >
              {{ item }}
            </button>
          </div>
          <label>补充读者要求
            <textarea v-model="recreationTargetAudience" rows="3" placeholder="例如：18–35 岁；接受强情绪冲突；内容分级 16+" />
          </label>
        </fieldset>
        <label>发行与阅读场景
          <input v-model="recreationDistributionContext" placeholder="例如：女性向付费连载；移动端短章节阅读" />
        </label>
        <label>作者明确不可放弃的内容
          <textarea v-model="recreationProtectedElements" rows="4" placeholder="核心情感、人物身份、关系变化、结局代价、文化特征等；可逐条列出" />
          <small class="muted">这些内容会进入变更治理。Agent 只能提出调整建议，不能静默改写。</small>
        </label>
      </div>
      <div v-else-if="step === 2 && medium === 'translation'" class="form-stack">
        <p class="eyebrow">02 · 选择源作品</p><h2>从库里选，还是上传文档？</h2>
        <div class="choice-grid" style="grid-template-columns:1fr 1fr">
          <button class="choice-card" :class="{ selected: translationTab === 'library' }" @click="translationTab = 'library'">
            <strong>从库里选</strong><span>已有的原创小说</span>
          </button>
          <button class="choice-card" :class="{ selected: translationTab === 'upload' }" @click="translationTab = 'upload'">
            <strong>上传文档</strong><span>TXT / PDF / DOCX</span>
          </button>
        </div>
        <div v-if="translationTab === 'library'">
          <div class="choice-grid" style="margin-top:12px">
            <button v-for="project in projects.items.filter(p => p.medium === 'novel')" :key="project.id" class="choice-card" :class="{ selected: translationSourceName === project.name }" @click="translationSourceName = project.name">
              <strong>{{ project.name }}</strong><span>小说 · 章节已就绪</span>
            </button>
          </div>
          <p v-if="projects.items.filter(p => p.medium === 'novel').length === 0" class="muted">暂无可翻译的原创小说。请先创建一部。</p>
        </div>
        <div v-else class="upload-area" style="margin-top:12px; padding:16px; border:2px dashed #ccc; border-radius:8px; text-align:center">
          <input type="file" accept=".txt,.pdf,.docx" @change="translationFile = ($event.target as HTMLInputElement).files?.[0] ?? null" />
          <p v-if="translationFile" style="margin-top:8px; color:#29463b">{{ translationFile.name }}</p>
          <p v-else style="color:#999;margin-top:8px">拖拽或点击上传 TXT / PDF / DOCX</p>
        </div>
        <label style="margin-top:12px">目标语言
          <select v-model="translationTarget">
            <option value="ja-JP">日本語</option>
            <option value="ko-KR">한국어</option>
            <option value="en-US">English</option>
            <option value="zh-CN">简体中文</option>
            <option value="zh-TW">繁體中文</option>
          </select>
        </label>
      </div>
      <div v-else-if="step === 2 && medium !== 'translation'">
        <p class="eyebrow">02 · 故事来源</p><h2>从空白开始，还是让素材重生？</h2>
        <div class="choice-grid">
          <button v-for="item in ([['original','原创','从一句设想建立完整世界'],['adaptation','改编','上传素材并保留引用定位']] as const)" :key="item[0]" class="choice-card" :class="{ selected: sourceMode === item[0] }" @click="sourceMode = item[0]">
            <strong>{{ item[1] }}</strong><span>{{ item[2] }}</span>
          </button>
        </div>
      </div>
      <div v-else-if="step === 3 && medium !== 'translation'" class="form-stack">
        <p class="eyebrow">03 · 创作方向</p><h2>给创作团队一枚指南针。</h2>
        <label>项目名称<input v-model="name" maxlength="200" placeholder="例如：雾港来信" /></label>
        <section class="inspiration-panel" :class="{ active: inspirationMode }">
          <div>
            <p class="eyebrow">灵感模式</p>
            <h3>先说一句你想写的故事。</h3>
            <p class="muted">创作搭档会结合当前类型 Skill 提出核心设想、风格与世界规则候选；采纳前不会覆盖你的输入。</p>
          </div>
          <button type="button" class="secondary" @click="inspirationMode = !inspirationMode">
            {{ inspirationMode ? '收起' : '开启灵感模式' }}
          </button>
          <div v-if="inspirationMode" class="inspiration-workbench">
            <label>一句话想法
              <textarea v-model="inspirationSeed" rows="3" maxlength="1000" placeholder="例如：一个能听见谎言的女孩，爱上了唯一无法被她听懂的人。" />
            </label>
            <button type="button" class="primary" :disabled="inspirationLoading || inspirationSeed.trim().length < 2" @click="generateInspiration">
              {{ inspirationLoading ? '创作搭档正在发散…' : '生成设定候选' }}
            </button>
            <p v-if="inspirationError" class="form-error">{{ inspirationError }}</p>
            <article v-if="inspirationCandidate" class="inspiration-candidate">
              <p class="eyebrow">候选设定 · {{ inspirationCandidate.model_key }}</p>
              <h3>{{ inspirationCandidate.title }}</h3>
              <dl>
                <div><dt>核心设想</dt><dd>{{ inspirationCandidate.premise }}</dd></div>
                <div><dt>风格边界</dt><dd>{{ inspirationCandidate.tone }}</dd></div>
                <div><dt>世界规则</dt><dd>{{ inspirationCandidate.world_setting }}</dd></div>
              </dl>
              <ul v-if="inspirationCandidate.questions.length">
                <li v-for="question in inspirationCandidate.questions" :key="question">{{ question }}</li>
              </ul>
              <div class="candidate-actions">
                <span class="muted">将填入下方表单，之后仍可逐项修改。</span>
                <button type="button" class="primary" @click="applyInspiration">采纳并继续编辑</button>
              </div>
            </article>
          </div>
        </section>
        <fieldset class="genre-picker">
          <legend>类型</legend>
          <div class="genre-tools">
            <input v-model="genreSearch" type="search" placeholder="搜索类型" aria-label="搜索类型" />
            <button v-if="!genreSearch" type="button" class="secondary" @click="showAllGenres = !showAllGenres">
              {{ showAllGenres ? '收起类型' : `查看全部 ${genreOptions.length} 类` }}
            </button>
          </div>
          <div class="genre-presets" aria-label="常用类型（可多选）">
            <button v-for="item in visibleGenrePresets" :key="item.key" type="button" :class="{ selected: selectedGenres.includes(item.key) }" :aria-pressed="selectedGenres.includes(item.key)" :title="`由 ${item.skill_keys.join('、')} 支持`" @click="toggleGenre(item.key)">{{ creativeLanguage === 'en-US' ? item.label_en : item.label_zh }}</button>
          </div>
          <small v-if="genreSearch && visibleGenrePresets.length === 0" class="muted">没有匹配的已准入类型，可使用下方自定义类型。</small>
          <small v-if="genreOptionsLoading" class="muted">正在读取可用 Skill 类型…</small>
          <label>自定义类型
            <input v-model="customGenre" placeholder="输入其他类型，多个类型用逗号分隔" />
          </label>
          <small class="muted">可多选；可见选项来自当前已通过准入的 Skill，自定义类型也会参与能力匹配。</small>
        </fieldset>
        <label>核心设想<textarea v-model="premise" rows="5" placeholder="谁，在什么处境中，必须完成什么？" /></label>
        <label>风格气质与创作边界
          <textarea v-model="tone" rows="3" placeholder="例如：克制、冷峻、少解释；避免宿命论与廉价煽情" />
          <small class="muted">描述叙述声音、情绪质感，以及 Agent 必须避免的表达方式。</small>
        </label>
        <label>世界观与核心规则
          <textarea v-model="worldSetting" rows="4" placeholder="例如：记忆可以交易，但复制记忆不会复制人格；任何改写都会留下可追溯痕迹" />
          <small class="muted">描述这个世界如何运转、什么能够发生，以及不可违背的规则。</small>
        </label>
        <label>创作语言
          <select v-model="creativeLanguage" aria-describedby="creative-language-hint">
            <option disabled value="">请选择创作语言</option>
            <option value="zh-CN">简体中文</option>
            <option value="zh-TW">繁體中文</option>
            <option value="en-US">English</option>
            <option value="ja-JP">日本語</option>
            <option value="ko-KR">한국어</option>
          </select>
          <small id="creative-language-hint" class="muted">Agent 的创意、蓝图、正文与审读默认使用该语言。</small>
        </label>
        <label>叙事结构
          <select v-model="structure" required><option disabled value="">请选择叙事结构</option><option value="hero_journey">英雄之旅</option><option value="three_act">三幕结构</option><option value="five_act">五幕结构</option><option value="save_the_cat">救猫咪</option><option value="eight_sequence">八序列</option><option value="harmon_circle">哈蒙圆环</option><option value="freytag">弗雷塔格金字塔</option><option value="custom">自定义</option></select>
        </label>
        <label v-if="structure === 'custom'">自定义叙事结构
          <input v-model="customStructure" required placeholder="描述阶段、节拍或循环规则" />
        </label>
        <fieldset v-if="medium === 'script'" class="format-choice"><legend>剧本格式（创建后锁定）</legend><label><input v-model="scriptFormat" type="radio" value="chinese" /> 中国剧本格式</label><label><input v-model="scriptFormat" type="radio" value="hollywood" /> 好莱坞标准格式</label></fieldset>
        <div class="volume-grid">
          <label>{{ medium === 'script' ? '篇章数量' : '卷数' }}<input v-model.number="volumeOne" type="number" min="1" required placeholder="请填写" /></label>
          <label>{{ medium === 'script' ? '每章场景' : '每卷章节' }}<input v-model.number="volumeTwo" type="number" min="1" required placeholder="请填写" /></label>
          <label v-if="medium === 'script'">场景节奏（分钟）<input v-model.number="volumeThree" type="number" min="1" required placeholder="请填写" /></label>
          <label v-else>每章目标词数
            <input
              v-model.number="novelChapterTargetWords"
              type="number"
              min="1"
              step="50"
              required
              placeholder="填写单章目标词数"
              aria-describedby="chapter-target-words-hint"
            />
          </label>
          <small
            v-if="medium !== 'script'"
            id="chapter-target-words-hint"
            class="muted volume-grid-hint"
          >
            这是每一章的目标，而非全书总量；写作与审读会读取此设置。
          </small>
        </div>
        <label v-if="sourceMode === 'adaptation'">改编素材
          <input type="file" accept=".txt,.pdf,.docx" required @change="sourceFile = ($event.target as HTMLInputElement).files?.[0] ?? null" />
          <small class="muted">支持 TXT、PDF、DOCX；内容会经过类型识别和隔离检查。</small>
        </label>
      </div>
      <div v-else-if="workflowKind === 'cross_cultural_recreation'" class="review-panel">
        <p class="eyebrow">04 · 确认归化任务</p>
        <h2>{{ name }}</h2>
        <dl>
          <div><dt>工作流</dt><dd>故事归化 · 跨文化故事再创作</dd></div>
          <div><dt>源作品</dt><dd>{{ sourceFile?.name }}</dd></div>
          <div><dt>创作方向</dt><dd>{{ recreationSourceLanguage }} → {{ recreationTargetLanguage }}</dd></div>
          <div><dt>目标市场</dt><dd>{{ combinedTargetMarket }}</dd></div>
          <div><dt>目标读者</dt><dd>{{ combinedTargetAudience }}</dd></div>
          <div><dt>发行场景</dt><dd>{{ recreationDistributionContext || '暂无' }}</dd></div>
          <div><dt>保护内容</dt><dd>{{ recreationProtectedElements || '暂无' }}</dd></div>
        </dl>
        <p class="muted">创建后先进行源作品分析和策略比较；确认试写方向前不会自动展开整部作品。</p>
      </div>
      <div v-else-if="medium === 'translation'" class="review-panel">
        <p class="eyebrow">04 · 确认种子</p><h2>{{ translationSourceName || '选择源作品' }}</h2>
        <dl>
          <div><dt>形态</dt><dd>翻译（直译）</dd></div>
          <div><dt>源作品</dt><dd>{{ translationSourceName || '未选择' }}</dd></div>
          <div><dt>目标语言</dt><dd>{{ ({ 'ja-JP': '日本語', 'ko-KR': '한국어', 'en-US': 'English', 'zh-CN': '简体中文', 'zh-TW': '繁體中文' } as Record<string, string>)[translationTarget || 'ja-JP'] }}</dd></div>
          <div><dt>翻译模式</dt><dd>忠实直译</dd></div>
        </dl>
      </div>
      <div v-else class="review-panel">
        <p class="eyebrow">04 · 确认种子</p><h2>{{ name }}</h2>
        <dl><div><dt>形态</dt><dd>{{ medium === 'script' ? `剧本 · ${scriptFormat === 'chinese' ? '中国格式' : '好莱坞格式'}` : '小说' }}</dd></div><div><dt>来源</dt><dd>{{ sourceMode === 'original' ? '原创' : `改编 · ${sourceFile?.name || '尚未选择素材'}` }}</dd></div><div><dt>类型</dt><dd>{{ genre || '未指定' }}</dd></div><div><dt>创作语言</dt><dd>{{ ({ 'zh-CN': '简体中文', 'zh-TW': '繁體中文', 'en-US': 'English', 'ja-JP': '日本語', 'ko-KR': '한국어' } as Record<string, string>)[creativeLanguage] }}</dd></div><div><dt>结构</dt><dd>{{ structure }}</dd></div><div><dt>体量</dt><dd>{{ medium === 'novel' ? `${volumeOne} 卷 × ${volumeTwo} 章/卷 · 每章 ${novelChapterTargetWords} 词` : `${volumeOne} / ${volumeTwo} / ${volumeThree}` }}</dd></div><div><dt>核心设想</dt><dd>{{ premise }}</dd></div><div><dt>世界规则</dt><dd>{{ worldSetting || '由 Agent 在创意阶段提出' }}</dd></div><div><dt>风格边界</dt><dd>{{ tone || '未指定' }}</dd></div></dl>
      </div>
      <footer class="wizard-actions">
        <p v-if="submissionError" class="form-error wizard-submit-error" role="alert">
          {{ submissionError }}
        </p>
        <button v-if="step > 1" class="secondary" @click="step--">上一步</button>
        <span />
        <button v-if="step < 4" class="primary" :disabled="!canContinue" @click="step++">继续</button>
        <button v-else class="primary" :disabled="submitting" @click="finish">{{ submitting ? '正在创建…' : '创建并进入' }}</button>
      </footer>
    </section>
  </AppShell>
</template>
