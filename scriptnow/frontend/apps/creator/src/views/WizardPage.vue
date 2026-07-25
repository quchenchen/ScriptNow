<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import AppShell from '../components/AppShell.vue'
import { useProjectsStore } from '../stores/projects'
import type { Medium, SourceMode } from '../types'

const step = ref(1)
const medium = ref<Medium | null>(null)
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
const translationSourceName = ref('')
const translationTarget = ref('ja-JP')
const projects = useProjectsStore()
const router = useRouter()
const genrePresets = computed(() =>
  medium.value === 'script'
    ? ['悬疑', '科幻', '犯罪', '爱情', '喜剧', '动作', '历史', '家庭']
    : ['悬疑', '科幻', '奇幻', '爱情', '都市', '历史', '成长', '现实主义'],
)
const genre = computed(() =>
  [...selectedGenres.value, ...customGenre.value.split(/[,，、/]/)]
    .map((item) => item.trim())
    .filter((item, index, items) => item && items.indexOf(item) === index)
    .join(', '),
)
const canContinue = computed(
  () => {
    if (step.value === 1) return medium.value !== null
    if (medium.value === 'translation') return true  // skip to submit
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

async function finish() {
  if (medium.value === 'translation') {
    // Call translation API directly
    submitting.value = true
    try {
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
    } finally { submitting.value = false }
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
          <button v-for="item in ([['script','剧本','以场景、动作和对白推进'],['novel','小说','以章节、叙述和内心推进'],['translation','翻译','直译文学作品到目标语言']] as const)" :key="item[0]" class="choice-card" :class="{ selected: medium === item[0] }" @click="medium = item[0]">
            <strong>{{ item[1] }}</strong><span>{{ item[2] }}</span>
          </button>
        </div>
      </div>
      <div v-else-if="step === 2 && medium === 'translation'" class="form-stack">
        <p class="eyebrow">02 · 选择源作品</p><h2>要翻译哪部小说？</h2>
        <div class="choice-grid">
          <button v-for="project in projects.items.filter(p => p.medium === 'novel')" :key="project.id" class="choice-card" :class="{ selected: translationSourceName === project.name }" @click="translationSourceName = project.name">
            <strong>{{ project.name }}</strong><span>小说 · 章节已就绪</span>
          </button>
        </div>
        <p v-if="projects.items.filter(p => p.medium === 'novel').length === 0" class="muted">暂无可翻译的原创小说。请先创建一部。</p>
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
        <fieldset class="genre-picker">
          <legend>类型</legend>
          <div class="genre-presets" aria-label="常用类型（可多选）">
            <button v-for="item in genrePresets" :key="item" type="button" :class="{ selected: selectedGenres.includes(item) }" :aria-pressed="selectedGenres.includes(item)" @click="toggleGenre(item)">{{ item }}</button>
          </div>
          <label>自定义类型
            <input v-model="customGenre" placeholder="输入其他类型，多个类型用逗号分隔" />
          </label>
          <small class="muted">可多选；预选与自定义类型会共同参与 Skill 匹配。</small>
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
            <input v-model.number="novelChapterTargetWords" type="number" min="1" step="50" required placeholder="填写单章目标词数" />
            <small class="muted">这是每一章的目标，而非全书总量；写作与审读会读取此设置。</small>
          </label>
        </div>
        <label v-if="sourceMode === 'adaptation'">改编素材
          <input type="file" accept=".txt,.pdf,.docx" required @change="sourceFile = ($event.target as HTMLInputElement).files?.[0] ?? null" />
          <small class="muted">支持 TXT、PDF、DOCX；内容会经过类型识别和隔离检查。</small>
        </label>
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
        <button v-if="step > 1" class="secondary" @click="step--">上一步</button>
        <span />
        <button v-if="step < 4" class="primary" :disabled="!canContinue" @click="step++">继续</button>
        <button v-else class="primary" :disabled="submitting" @click="finish">{{ submitting ? '正在创建…' : '创建并进入' }}</button>
      </footer>
    </section>
  </AppShell>
</template>
