import { computed, onMounted, ref } from 'vue';
import { revisionPayload, selectionFromRange } from './revision';
const API = 'http://127.0.0.1:8100';
const screen = ref('dashboard'), step = ref(1), goal = ref('original-script');
const title = ref(''), seed = ref(''), genre = ref('悬疑'), audience = ref('大众'), sourceName = ref('');
const sourceMethod = ref('paste'), sourceFile = ref(null);
const mode = ref('focus');
const projects = ref([]), current = ref(null), continuity = ref(null), manuscript = ref(null), busy = ref(false), error = ref('');
const runtime = ref(null);
const directiveText = ref(''), directiveScope = ref('next_task'), directives = ref([]), directiveNotice = ref('');
const selectedText = ref(null), revisionInstruction = ref(''), replacementText = ref(''), revision = ref(null);
const goals = [
    { key: 'original-novel', title: '创作一部小说', desc: '从主题、灵感或大纲开始生长' },
    { key: 'original-script', title: '创作一个剧本', desc: '从故事种子长成 Episode 与 Scene' },
    { key: 'adapt-novel', title: '把剧本或故事改编成小说', desc: '从已有故事出发，重构视角与文风' },
    { key: 'adapt-script', title: '把小说或故事改编成剧本', desc: '从已有文本出发，映射为可拍摄 Scene' },
];
const isAdapt = computed(() => goal.value.startsWith('adapt'));
const isNovel = computed(() => goal.value.endsWith('novel'));
const goalLabel = computed(() => goals.find(x => x.key === goal.value)?.title || '');
const firstTask = computed(() => isAdapt.value ? '改编策划师解析来源并提交 Adaptation Map 候选' : '创意导演基于种子提交 3 个差异化 Story Core 候选');
function begin() { step.value = 1; screen.value = 'create'; }
function next() { if (step.value < 4)
    step.value++;
else
    void createProject(); }
function pickFile(event) { sourceFile.value = event.target.files?.[0] || null; }
async function createProject() { busy.value = true; error.value = ''; try {
    const response = await fetch(`${API}/projects`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: title.value || '未命名作品', goal_type: goal.value, seed: seed.value, genre: genre.value, audience: audience.value, source_name: sourceName.value, source_type: isAdapt.value ? (sourceMethod.value === 'upload' ? 'file_reference' : 'pasted_text') : 'none', source_content: isAdapt.value && sourceMethod.value === 'paste' ? seed.value : '', source_file_name: sourceFile.value?.name || '' }) });
    if (!response.ok)
        throw new Error('项目创建失败，请确认本地后端已启动');
    current.value = await response.json();
    projects.value.unshift(current.value);
    screen.value = 'workspace';
    mode.value = 'focus';
    await runFirstTask();
}
catch (e) {
    error.value = e instanceof Error ? e.message : '项目创建失败';
}
finally {
    busy.value = false;
} }
async function refreshCurrent() { if (!current.value)
    return; const r = await fetch(`${API}/projects/${current.value.id}`); if (r.ok) {
    const updated = await r.json();
    current.value = updated;
    const index = projects.value.findIndex(p => p.id === updated.id);
    if (index >= 0)
        projects.value[index] = updated;
} }
async function runFirstTask() { if (!current.value?.task || current.value.task.status === 'waiting_decision')
    return; busy.value = true; try {
    const r = await fetch(`${API}/projects/${current.value.id}/tasks/${current.value.task.id}/run`, { method: 'POST' });
    if (!r.ok)
        throw new Error('Agent 任务执行失败');
    current.value.task = await r.json();
    await refreshCurrent();
    mode.value = 'review';
}
catch (e) {
    error.value = e instanceof Error ? e.message : 'Agent 任务执行失败';
}
finally {
    busy.value = false;
} }
async function loadContinuity() { if (!current.value?.adopted_story_core_id)
    return; const r = await fetch(`${API}/projects/${current.value.id}/continuity`); if (r.ok)
    continuity.value = await r.json(); }
async function adopt(candidate) { if (!current.value)
    return; busy.value = true; try {
    const r = await fetch(`${API}/projects/${current.value.id}/story-cores/${candidate.id}/adopt`, { method: 'POST' });
    if (!r.ok)
        throw new Error('采用失败');
    current.value = await r.json();
    await loadContinuity();
    mode.value = 'plan';
}
catch (e) {
    error.value = e instanceof Error ? e.message : '采用失败';
}
finally {
    busy.value = false;
} }
async function draftOpening() { if (!current.value)
    return; busy.value = true; error.value = ''; try {
    const r = await fetch(`${API}/projects/${current.value.id}/manuscript/next`, { method: 'POST' });
    if (!r.ok)
        throw new Error('正文候选生成失败');
    manuscript.value = await r.json();
    await refreshCurrent();
    mode.value = 'focus';
}
catch (e) {
    error.value = e instanceof Error ? e.message : '正文候选生成失败';
}
finally {
    busy.value = false;
} }
async function adoptOpening() { if (!current.value || !manuscript.value?.candidate)
    return; busy.value = true; try {
    const r = await fetch(`${API}/projects/${current.value.id}/manuscript/${manuscript.value.candidate.id}/adopt`, { method: 'POST' });
    if (!r.ok)
        throw new Error('正文采用失败');
    manuscript.value = await r.json();
    await Promise.all([loadContinuity(), refreshCurrent()]);
}
catch (e) {
    error.value = e instanceof Error ? e.message : '正文采用失败';
}
finally {
    busy.value = false;
} }
function captureSelection(event) { const target = event.target; selectedText.value = selectionFromRange(target.value, target.selectionStart, target.selectionEnd); if (selectedText.value)
    replacementText.value = selectedText.value.text; }
async function createSelectionRevision() { if (!current.value || !manuscript.value?.scene_id || !selectedText.value || !revisionInstruction.value.trim() || !replacementText.value.trim())
    return; busy.value = true; error.value = ''; try {
    const payload = revisionPayload(manuscript.value.adopted_content, selectedText.value, revisionInstruction.value, replacementText.value);
    const r = await fetch(`${API}/projects/${current.value.id}/revisions`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scene_id: manuscript.value.scene_id, ...payload }) });
    if (!r.ok)
        throw new Error('Revision 候选创建失败');
    revision.value = await r.json();
}
catch (e) {
    error.value = e instanceof Error ? e.message : 'Revision 候选创建失败';
}
finally {
    busy.value = false;
} }
async function resolveSelectionRevision(action) { if (!current.value || !revision.value)
    return; busy.value = true; error.value = ''; try {
    const r = await fetch(`${API}/projects/${current.value.id}/revisions/${revision.value.id}/${action}`, { method: 'POST' });
    if (r.status === 409) {
        revision.value = { ...revision.value, status: 'stale', stale_reason: '基线内容已变化，请重新比较' };
        return;
    }
    if (!r.ok)
        throw new Error(action === 'adopt' ? '采用 Revision 失败' : '拒绝 Revision 失败');
    const resolved = await r.json();
    revision.value = resolved;
    if (action === 'adopt' && manuscript.value)
        manuscript.value.adopted_content = resolved.candidate_content;
}
catch (e) {
    error.value = e instanceof Error ? e.message : 'Revision 处理失败';
}
finally {
    busy.value = false;
} }
async function restartSelectionRevision() { revision.value = null; selectedText.value = null; revisionInstruction.value = ''; replacementText.value = ''; if (current.value) {
    const r = await fetch(`${API}/projects/${current.value.id}/manuscript/latest`);
    if (r.ok)
        manuscript.value = await r.json();
} }
async function loadRuntime() { try {
    const r = await fetch(`${API}/runtime/status`);
    if (r.ok)
        runtime.value = await r.json();
}
catch { /* 顶栏保持离线状态 */ } }
async function loadDirectives() { if (!current.value)
    return; const r = await fetch(`${API}/projects/${current.value.id}/directives`); if (r.ok)
    directives.value = await r.json(); }
async function submitDirective() { if (!current.value || !directiveText.value.trim())
    return; busy.value = true; try {
    const r = await fetch(`${API}/projects/${current.value.id}/directives`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scope: directiveScope.value, instruction: directiveText.value.trim(), preserve: [], constraints: [] }) });
    if (!r.ok)
        throw new Error('创作指令保存失败');
    const saved = await r.json();
    directives.value.unshift(saved);
    directiveNotice.value = directiveScope.value === 'next_task' ? '已进入下一次任务的 Context Pack' : '已成为项目长期创作规则';
    directiveText.value = '';
}
catch (e) {
    error.value = e instanceof Error ? e.message : '创作指令保存失败';
}
finally {
    busy.value = false;
} }
async function openProject(p) { current.value = p; title.value = p.title; goal.value = p.goal_type; seed.value = p.seed; continuity.value = null; manuscript.value = null; revision.value = null; selectedText.value = null; directives.value = []; directiveNotice.value = ''; screen.value = 'workspace'; await loadDirectives(); if (p.adopted_story_core_id) {
    await loadContinuity();
    const r = await fetch(`${API}/projects/${p.id}/manuscript/latest`);
    if (r.ok)
        manuscript.value = await r.json();
} }
function reset() { title.value = ''; seed.value = ''; sourceName.value = ''; step.value = 1; screen.value = 'dashboard'; }
onMounted(async () => { await loadRuntime(); try {
    const r = await fetch(`${API}/projects`);
    if (r.ok)
        projects.value = await r.json();
}
catch { /* 后端状态由创建动作明确提示 */ } });
const __VLS_ctx = {
    ...{},
    ...{},
};
let __VLS_components;
let __VLS_intrinsics;
let __VLS_directives;
__VLS_asFunctionalElement1(__VLS_intrinsics.main, __VLS_intrinsics.main)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.header, __VLS_intrinsics.header)({
    ...{ class: "top" },
});
/** @type {__VLS_StyleScopedClasses['top']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.strong, __VLS_intrinsics.strong)({});
if (__VLS_ctx.screen === 'workspace') {
    __VLS_asFunctionalElement1(__VLS_intrinsics.nav, __VLS_intrinsics.nav)({});
    for (const [m] of __VLS_vFor(([{ k: 'focus', n: '专注创作' }, { k: 'plan', n: '故事规划' }, { k: 'review', n: '审阅决策' }]))) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.screen === 'workspace'))
                        throw 0;
                    return (__VLS_ctx.mode = m.k);
                    // @ts-ignore
                    [screen, mode, mode,];
                } },
            key: (m.k),
            ...{ class: ({ active: __VLS_ctx.mode === m.k }) },
        });
        /** @type {__VLS_StyleScopedClasses['active']} */ ;
        (m.n);
        // @ts-ignore
        [mode,];
    }
}
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
    ...{ class: (['runtime-pill', __VLS_ctx.runtime?.mode]) },
});
/** @type {__VLS_StyleScopedClasses['runtime-pill']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.i, __VLS_intrinsics.i)({});
(__VLS_ctx.runtime?.capability_tier || '创作引擎连接中');
if (__VLS_ctx.screen !== 'dashboard') {
    __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
        ...{ onClick: (__VLS_ctx.reset) },
        ...{ class: "quiet" },
    });
    /** @type {__VLS_StyleScopedClasses['quiet']} */ ;
}
if (__VLS_ctx.screen === 'dashboard') {
    __VLS_asFunctionalElement1(__VLS_intrinsics.section, __VLS_intrinsics.section)({
        ...{ class: "dashboard" },
    });
    /** @type {__VLS_StyleScopedClasses['dashboard']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "hero" },
    });
    /** @type {__VLS_StyleScopedClasses['hero']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({
        ...{ class: "kicker" },
    });
    /** @type {__VLS_StyleScopedClasses['kicker']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.h1, __VLS_intrinsics.h1)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
        ...{ onClick: (__VLS_ctx.begin) },
        ...{ class: "primary" },
    });
    /** @type {__VLS_StyleScopedClasses['primary']} */ ;
    if (__VLS_ctx.projects.length) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "projects" },
        });
        /** @type {__VLS_StyleScopedClasses['projects']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "projects-head" },
        });
        /** @type {__VLS_StyleScopedClasses['projects-head']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.h2, __VLS_intrinsics.h2)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
        (__VLS_ctx.projects.filter(p => p.pulse?.needs_user).length);
        for (const [p] of __VLS_vFor((__VLS_ctx.projects))) {
            __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.screen === 'dashboard'))
                            throw 0;
                        if (!(__VLS_ctx.projects.length))
                            throw 0;
                        return (__VLS_ctx.openProject(p));
                        // @ts-ignore
                        [screen, screen, runtime, runtime, reset, begin, projects, projects, projects, openProject,];
                    } },
                key: (p.id),
                ...{ class: "project" },
            });
            /** @type {__VLS_StyleScopedClasses['project']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
            __VLS_asFunctionalElement1(__VLS_intrinsics.strong, __VLS_intrinsics.strong)({});
            (p.title);
            __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
            (__VLS_ctx.goals.find(x => x.key === p.goal_type)?.title);
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                ...{ class: "project-next" },
            });
            /** @type {__VLS_StyleScopedClasses['project-next']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.b, __VLS_intrinsics.b)({
                ...{ class: (['pulse-state', p.pulse?.state]) },
            });
            /** @type {__VLS_StyleScopedClasses['pulse-state']} */ ;
            (p.pulse?.needs_user ? '等待你的判断' : p.pulse?.state === 'working' ? 'Agent 工作中' : '可继续');
            __VLS_asFunctionalElement1(__VLS_intrinsics.small, __VLS_intrinsics.small)({});
            (p.pulse?.headline);
            // @ts-ignore
            [goals,];
        }
    }
}
else if (__VLS_ctx.screen === 'create') {
    __VLS_asFunctionalElement1(__VLS_intrinsics.section, __VLS_intrinsics.section)({
        ...{ class: "create" },
    });
    /** @type {__VLS_StyleScopedClasses['create']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "steps" },
    });
    /** @type {__VLS_StyleScopedClasses['steps']} */ ;
    for (const [n] of __VLS_vFor((4))) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
            key: (n),
            ...{ class: ({ on: n <= __VLS_ctx.step }) },
        });
        /** @type {__VLS_StyleScopedClasses['on']} */ ;
        (n);
        // @ts-ignore
        [screen, step,];
    }
    if (__VLS_ctx.step === 1) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({
            ...{ class: "kicker" },
        });
        /** @type {__VLS_StyleScopedClasses['kicker']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.h1, __VLS_intrinsics.h1)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "goal-grid" },
        });
        /** @type {__VLS_StyleScopedClasses['goal-grid']} */ ;
        for (const [g] of __VLS_vFor((__VLS_ctx.goals))) {
            __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
                ...{ onClick: (...[$event]) => {
                        if (!!(__VLS_ctx.screen === 'dashboard'))
                            throw 0;
                        if (!(__VLS_ctx.screen === 'create'))
                            throw 0;
                        if (!(__VLS_ctx.step === 1))
                            throw 0;
                        return (__VLS_ctx.goal = g.key);
                        // @ts-ignore
                        [goals, step, goal,];
                    } },
                key: (g.key),
                ...{ class: (['goal', { selected: __VLS_ctx.goal === g.key }]) },
            });
            /** @type {__VLS_StyleScopedClasses['selected']} */ ;
            /** @type {__VLS_StyleScopedClasses['goal']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.strong, __VLS_intrinsics.strong)({});
            (g.title);
            __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
            (g.desc);
            // @ts-ignore
            [goal,];
        }
    }
    if (__VLS_ctx.step === 2) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({
            ...{ class: "kicker" },
        });
        /** @type {__VLS_StyleScopedClasses['kicker']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.h1, __VLS_intrinsics.h1)({});
        (__VLS_ctx.isAdapt ? '提供可用的作品来源' : '先给团队一颗种子');
        __VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.input)({
            placeholder: "例如：雾港来信",
        });
        (__VLS_ctx.title);
        if (__VLS_ctx.isAdapt) {
            __VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({});
            __VLS_asFunctionalElement1(__VLS_intrinsics.input)({
                placeholder: "作品名称",
            });
            (__VLS_ctx.sourceName);
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                ...{ class: "form-grid" },
            });
            /** @type {__VLS_StyleScopedClasses['form-grid']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({});
            __VLS_asFunctionalElement1(__VLS_intrinsics.input)({
                type: "radio",
                value: "paste",
            });
            (__VLS_ctx.sourceMethod);
            __VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({});
            __VLS_asFunctionalElement1(__VLS_intrinsics.input)({
                type: "radio",
                value: "upload",
            });
            (__VLS_ctx.sourceMethod);
            if (__VLS_ctx.sourceMethod === 'upload') {
                __VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({});
                __VLS_asFunctionalElement1(__VLS_intrinsics.input)({
                    ...{ onChange: (__VLS_ctx.pickFile) },
                    type: "file",
                    accept: ".txt,.docx,.pdf",
                });
                __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
                (__VLS_ctx.sourceFile?.name || '支持 TXT、DOCX、PDF');
            }
            else {
                __VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({});
                __VLS_asFunctionalElement1(__VLS_intrinsics.textarea)({
                    value: (__VLS_ctx.seed),
                    rows: "7",
                    placeholder: "可以是完整文本，也可以先提供足以建立改编依据的梗概与核心片段",
                });
            }
        }
        else {
            __VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({});
            __VLS_asFunctionalElement1(__VLS_intrinsics.textarea)({
                value: (__VLS_ctx.seed),
                rows: "7",
                placeholder: "不必完整，一句话也可以；已有草稿也可以直接粘贴",
            });
        }
    }
    if (__VLS_ctx.step === 3) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({
            ...{ class: "kicker" },
        });
        /** @type {__VLS_StyleScopedClasses['kicker']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.h1, __VLS_intrinsics.h1)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "form-grid" },
        });
        /** @type {__VLS_StyleScopedClasses['form-grid']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.select, __VLS_intrinsics.select)({
            value: (__VLS_ctx.genre),
        });
        __VLS_asFunctionalElement1(__VLS_intrinsics.option, __VLS_intrinsics.option)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.option, __VLS_intrinsics.option)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.option, __VLS_intrinsics.option)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.option, __VLS_intrinsics.option)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.option, __VLS_intrinsics.option)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.select, __VLS_intrinsics.select)({
            value: (__VLS_ctx.audience),
        });
        __VLS_asFunctionalElement1(__VLS_intrinsics.option, __VLS_intrinsics.option)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.option, __VLS_intrinsics.option)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.option, __VLS_intrinsics.option)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.option, __VLS_intrinsics.option)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "note" },
        });
        /** @type {__VLS_StyleScopedClasses['note']} */ ;
    }
    if (__VLS_ctx.step === 4) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({
            ...{ class: "kicker" },
        });
        /** @type {__VLS_StyleScopedClasses['kicker']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.h1, __VLS_intrinsics.h1)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.dl, __VLS_intrinsics.dl)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.dt, __VLS_intrinsics.dt)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.dd, __VLS_intrinsics.dd)({});
        (__VLS_ctx.goalLabel);
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.dt, __VLS_intrinsics.dt)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.dd, __VLS_intrinsics.dd)({});
        (__VLS_ctx.title || '未命名作品');
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.dt, __VLS_intrinsics.dt)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.dd, __VLS_intrinsics.dd)({});
        (__VLS_ctx.isNovel ? 'Volume / Chapter' : 'Episode / Scene');
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.dt, __VLS_intrinsics.dt)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.dd, __VLS_intrinsics.dd)({});
        (__VLS_ctx.firstTask);
        __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({
            ...{ class: "note" },
        });
        /** @type {__VLS_StyleScopedClasses['note']} */ ;
    }
    if (__VLS_ctx.error) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({
            ...{ class: "error" },
        });
        /** @type {__VLS_StyleScopedClasses['error']} */ ;
        (__VLS_ctx.error);
    }
    __VLS_asFunctionalElement1(__VLS_intrinsics.footer, __VLS_intrinsics.footer)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
        ...{ onClick: (...[$event]) => {
                if (!!(__VLS_ctx.screen === 'dashboard'))
                    throw 0;
                if (!(__VLS_ctx.screen === 'create'))
                    throw 0;
                return (__VLS_ctx.step--);
                // @ts-ignore
                [step, step, step, step, isAdapt, isAdapt, title, title, sourceName, sourceMethod, sourceMethod, sourceMethod, pickFile, sourceFile, seed, seed, genre, audience, goalLabel, isNovel, firstTask, error, error,];
            } },
        ...{ class: "secondary" },
        disabled: (__VLS_ctx.step === 1 || __VLS_ctx.busy),
    });
    /** @type {__VLS_StyleScopedClasses['secondary']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
        ...{ onClick: (__VLS_ctx.next) },
        ...{ class: "primary" },
        disabled: (__VLS_ctx.busy),
    });
    /** @type {__VLS_StyleScopedClasses['primary']} */ ;
    (__VLS_ctx.busy ? '团队正在准备…' : __VLS_ctx.step === 4 ? '创建并启动首个任务' : '继续');
}
else {
    __VLS_asFunctionalElement1(__VLS_intrinsics.section, __VLS_intrinsics.section)({
        ...{ class: "workspace" },
    });
    /** @type {__VLS_StyleScopedClasses['workspace']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.aside, __VLS_intrinsics.aside)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({
        ...{ class: "kicker" },
    });
    /** @type {__VLS_StyleScopedClasses['kicker']} */ ;
    (__VLS_ctx.isNovel ? 'CHAPTERS' : 'EPISODES / SCENES');
    __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
        ...{ class: "tree active" },
    });
    /** @type {__VLS_StyleScopedClasses['tree']} */ ;
    /** @type {__VLS_StyleScopedClasses['active']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
        ...{ class: "tree" },
    });
    /** @type {__VLS_StyleScopedClasses['tree']} */ ;
    (__VLS_ctx.manuscript ? `第 ${__VLS_ctx.manuscript.ordinal} ${__VLS_ctx.isNovel ? '章' : '场'}` : (__VLS_ctx.isNovel ? '第一章' : '第一场'));
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
    (__VLS_ctx.manuscript?.status === 'adopted' ? '已采用' : __VLS_ctx.manuscript ? '待判断' : '未开始');
    if (__VLS_ctx.current?.pulse) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.section, __VLS_intrinsics.section)({
            ...{ class: "pulse-card" },
        });
        /** @type {__VLS_StyleScopedClasses['pulse-card']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
            ...{ class: (['pulse-dot', __VLS_ctx.current.pulse.state]) },
        });
        /** @type {__VLS_StyleScopedClasses['pulse-dot']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.b, __VLS_intrinsics.b)({});
        (__VLS_ctx.current.pulse.headline);
        __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({});
        (__VLS_ctx.current.pulse.detail);
        __VLS_asFunctionalElement1(__VLS_intrinsics.small, __VLS_intrinsics.small)({});
        (__VLS_ctx.current.pulse.next_action);
        if (__VLS_ctx.current.pulse.estimated_credits) {
            __VLS_asFunctionalElement1(__VLS_intrinsics.small, __VLS_intrinsics.small)({});
            (__VLS_ctx.current.pulse.estimated_credits);
        }
    }
    if (__VLS_ctx.mode === 'focus') {
        __VLS_asFunctionalElement1(__VLS_intrinsics.article, __VLS_intrinsics.article)({
            ...{ class: "paper writing" },
        });
        /** @type {__VLS_StyleScopedClasses['paper']} */ ;
        /** @type {__VLS_StyleScopedClasses['writing']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.small, __VLS_intrinsics.small)({});
        (__VLS_ctx.current?.title || __VLS_ctx.title || '未命名作品');
        (__VLS_ctx.goalLabel);
        if (__VLS_ctx.manuscript?.candidate) {
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                ...{ class: "draft-head" },
            });
            /** @type {__VLS_StyleScopedClasses['draft-head']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
            __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
                ...{ class: "kicker" },
            });
            /** @type {__VLS_StyleScopedClasses['kicker']} */ ;
            (__VLS_ctx.manuscript.status === 'adopted' ? 'ADOPTED · 已进入正文' : 'CANDIDATE · 尚未写入正文');
            __VLS_asFunctionalElement1(__VLS_intrinsics.h1, __VLS_intrinsics.h1)({});
            (__VLS_ctx.manuscript.title);
            __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
                ...{ class: "health stable" },
            });
            /** @type {__VLS_StyleScopedClasses['health']} */ ;
            /** @type {__VLS_StyleScopedClasses['stable']} */ ;
            if (__VLS_ctx.manuscript.status === 'adopted') {
                __VLS_asFunctionalElement1(__VLS_intrinsics.textarea, __VLS_intrinsics.textarea)({
                    ...{ onSelect: (__VLS_ctx.captureSelection) },
                    ...{ onMouseup: (__VLS_ctx.captureSelection) },
                    ...{ onKeyup: (__VLS_ctx.captureSelection) },
                    ...{ class: "manuscript manuscript-editor" },
                    value: (__VLS_ctx.manuscript.adopted_content),
                    readonly: true,
                    'aria-label': "已采用 Scene 正文",
                });
                /** @type {__VLS_StyleScopedClasses['manuscript']} */ ;
                /** @type {__VLS_StyleScopedClasses['manuscript-editor']} */ ;
            }
            else {
                __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                    ...{ class: "manuscript" },
                });
                /** @type {__VLS_StyleScopedClasses['manuscript']} */ ;
                (__VLS_ctx.manuscript.candidate.content);
            }
            if (__VLS_ctx.manuscript.status === 'adopted' && __VLS_ctx.manuscript.unit_type === 'scene') {
                __VLS_asFunctionalElement1(__VLS_intrinsics.section, __VLS_intrinsics.section)({
                    ...{ class: "revision-workbench" },
                });
                /** @type {__VLS_StyleScopedClasses['revision-workbench']} */ ;
                __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                    ...{ class: "section-title" },
                });
                /** @type {__VLS_StyleScopedClasses['section-title']} */ ;
                __VLS_asFunctionalElement1(__VLS_intrinsics.b, __VLS_intrinsics.b)({});
                __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
                if (!__VLS_ctx.selectedText && !__VLS_ctx.revision) {
                    __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({});
                }
                else if (__VLS_ctx.selectedText && !__VLS_ctx.revision) {
                    __VLS_asFunctionalElement1(__VLS_intrinsics.blockquote, __VLS_intrinsics.blockquote)({});
                    (__VLS_ctx.selectedText.text);
                    __VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({});
                    __VLS_asFunctionalElement1(__VLS_intrinsics.input)({
                        placeholder: "例如：让对白更克制，但保留人物的试探",
                    });
                    (__VLS_ctx.revisionInstruction);
                    __VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({});
                    __VLS_asFunctionalElement1(__VLS_intrinsics.textarea, __VLS_intrinsics.textarea)({
                        value: (__VLS_ctx.replacementText),
                        rows: "4",
                    });
                    __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
                        ...{ onClick: (__VLS_ctx.createSelectionRevision) },
                        ...{ class: "primary" },
                        disabled: (__VLS_ctx.busy || !__VLS_ctx.revisionInstruction.trim() || !__VLS_ctx.replacementText.trim()),
                    });
                    /** @type {__VLS_StyleScopedClasses['primary']} */ ;
                    (__VLS_ctx.busy ? 'Agent 正在准备候选…' : '生成 Candidate Revision');
                }
                else if (__VLS_ctx.revision) {
                    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                        ...{ class: (['revision-status', __VLS_ctx.revision.status]) },
                    });
                    /** @type {__VLS_StyleScopedClasses['revision-status']} */ ;
                    (__VLS_ctx.revision.status === 'candidate' ? '等待你的判断' : __VLS_ctx.revision.status === 'adopted' ? '已采用' : __VLS_ctx.revision.status === 'rejected' ? '已拒绝' : '需要重新比较');
                    __VLS_asFunctionalElement1(__VLS_intrinsics.h3, __VLS_intrinsics.h3)({});
                    (__VLS_ctx.revision.brief.goal);
                    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                        ...{ class: "diff" },
                    });
                    /** @type {__VLS_StyleScopedClasses['diff']} */ ;
                    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
                    __VLS_asFunctionalElement1(__VLS_intrinsics.small, __VLS_intrinsics.small)({});
                    __VLS_asFunctionalElement1(__VLS_intrinsics.del, __VLS_intrinsics.del)({});
                    (__VLS_ctx.revision.context_pack.anchors.selected_text);
                    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
                    __VLS_asFunctionalElement1(__VLS_intrinsics.small, __VLS_intrinsics.small)({});
                    __VLS_asFunctionalElement1(__VLS_intrinsics.ins, __VLS_intrinsics.ins)({});
                    (__VLS_ctx.replacementText);
                    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                        ...{ class: "revision-meta" },
                    });
                    /** @type {__VLS_StyleScopedClasses['revision-meta']} */ ;
                    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
                    (__VLS_ctx.revision.brief.goal);
                    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
                    (__VLS_ctx.revision.brief.preserve.join('、'));
                    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
                    if (__VLS_ctx.revision.status === 'candidate') {
                        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                            ...{ class: "revision-actions" },
                        });
                        /** @type {__VLS_StyleScopedClasses['revision-actions']} */ ;
                        __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
                            ...{ onClick: (...[$event]) => {
                                    if (!!(__VLS_ctx.screen === 'dashboard'))
                                        throw 0;
                                    if (!!(__VLS_ctx.screen === 'create'))
                                        throw 0;
                                    if (!(__VLS_ctx.mode === 'focus'))
                                        throw 0;
                                    if (!(__VLS_ctx.manuscript?.candidate))
                                        throw 0;
                                    if (!(__VLS_ctx.manuscript.status === 'adopted' && __VLS_ctx.manuscript.unit_type === 'scene'))
                                        throw 0;
                                    if (!!(!__VLS_ctx.selectedText && !__VLS_ctx.revision))
                                        throw 0;
                                    if (!!(__VLS_ctx.selectedText && !__VLS_ctx.revision))
                                        throw 0;
                                    if (!(__VLS_ctx.revision))
                                        throw 0;
                                    if (!(__VLS_ctx.revision.status === 'candidate'))
                                        throw 0;
                                    return (__VLS_ctx.resolveSelectionRevision('reject'));
                                    // @ts-ignore
                                    [mode, step, step, title, goalLabel, isNovel, isNovel, isNovel, busy, busy, busy, busy, busy, next, manuscript, manuscript, manuscript, manuscript, manuscript, manuscript, manuscript, manuscript, manuscript, manuscript, manuscript, manuscript, current, current, current, current, current, current, current, current, captureSelection, captureSelection, captureSelection, selectedText, selectedText, selectedText, revision, revision, revision, revision, revision, revision, revision, revision, revision, revision, revision, revision, revisionInstruction, revisionInstruction, replacementText, replacementText, replacementText, createSelectionRevision, resolveSelectionRevision,];
                                } },
                            ...{ class: "secondary" },
                            disabled: (__VLS_ctx.busy),
                        });
                        /** @type {__VLS_StyleScopedClasses['secondary']} */ ;
                        __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
                            ...{ onClick: (...[$event]) => {
                                    if (!!(__VLS_ctx.screen === 'dashboard'))
                                        throw 0;
                                    if (!!(__VLS_ctx.screen === 'create'))
                                        throw 0;
                                    if (!(__VLS_ctx.mode === 'focus'))
                                        throw 0;
                                    if (!(__VLS_ctx.manuscript?.candidate))
                                        throw 0;
                                    if (!(__VLS_ctx.manuscript.status === 'adopted' && __VLS_ctx.manuscript.unit_type === 'scene'))
                                        throw 0;
                                    if (!!(!__VLS_ctx.selectedText && !__VLS_ctx.revision))
                                        throw 0;
                                    if (!!(__VLS_ctx.selectedText && !__VLS_ctx.revision))
                                        throw 0;
                                    if (!(__VLS_ctx.revision))
                                        throw 0;
                                    if (!(__VLS_ctx.revision.status === 'candidate'))
                                        throw 0;
                                    return (__VLS_ctx.resolveSelectionRevision('adopt'));
                                    // @ts-ignore
                                    [busy, resolveSelectionRevision,];
                                } },
                            ...{ class: "primary" },
                            disabled: (__VLS_ctx.busy),
                        });
                        /** @type {__VLS_StyleScopedClasses['primary']} */ ;
                    }
                    else if (__VLS_ctx.revision.status === 'stale') {
                        __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
                            ...{ onClick: (__VLS_ctx.restartSelectionRevision) },
                            ...{ class: "primary" },
                        });
                        /** @type {__VLS_StyleScopedClasses['primary']} */ ;
                    }
                    else {
                        __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
                            ...{ onClick: (__VLS_ctx.restartSelectionRevision) },
                            ...{ class: "secondary" },
                        });
                        /** @type {__VLS_StyleScopedClasses['secondary']} */ ;
                    }
                }
            }
            __VLS_asFunctionalElement1(__VLS_intrinsics.section, __VLS_intrinsics.section)({
                ...{ class: "change-preview" },
            });
            /** @type {__VLS_StyleScopedClasses['change-preview']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.b, __VLS_intrinsics.b)({});
            for (const [delta, name] of __VLS_vFor((__VLS_ctx.manuscript.candidate.state_delta))) {
                __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                    key: (name),
                });
                __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
                (name);
                __VLS_asFunctionalElement1(__VLS_intrinsics.small, __VLS_intrinsics.small)({});
                (delta);
                // @ts-ignore
                [busy, manuscript, revision, restartSelectionRevision, restartSelectionRevision,];
            }
            for (const [action] of __VLS_vFor((__VLS_ctx.manuscript.candidate.thread_actions))) {
                __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                    key: (action.note),
                });
                __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
                (action.action);
                __VLS_asFunctionalElement1(__VLS_intrinsics.small, __VLS_intrinsics.small)({});
                (action.note);
                // @ts-ignore
                [manuscript,];
            }
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                ...{ class: "checks" },
            });
            /** @type {__VLS_StyleScopedClasses['checks']} */ ;
            for (const [check] of __VLS_vFor((__VLS_ctx.manuscript.candidate.continuity_report))) {
                __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
                    key: (check.check),
                    ...{ class: (check.status) },
                });
                (check.message);
                // @ts-ignore
                [manuscript,];
            }
            if (__VLS_ctx.manuscript.status !== 'adopted') {
                __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
                    ...{ onClick: (__VLS_ctx.adoptOpening) },
                    ...{ class: "primary" },
                    disabled: (__VLS_ctx.busy),
                });
                /** @type {__VLS_StyleScopedClasses['primary']} */ ;
                (__VLS_ctx.busy ? '正在写入作品事实…' : '采用正文并更新叙事状态');
            }
            else {
                __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                    ...{ class: "truth" },
                });
                /** @type {__VLS_StyleScopedClasses['truth']} */ ;
                __VLS_asFunctionalElement1(__VLS_intrinsics.b, __VLS_intrinsics.b)({});
                __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
                __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
                    ...{ onClick: (__VLS_ctx.draftOpening) },
                    ...{ class: "primary" },
                    disabled: (__VLS_ctx.busy),
                });
                /** @type {__VLS_StyleScopedClasses['primary']} */ ;
                (__VLS_ctx.busy ? '写作者正在准备…' : `生成第 ${__VLS_ctx.manuscript.ordinal + 1} ${__VLS_ctx.isNovel ? '章' : '场'}候选`);
            }
        }
        else {
            __VLS_asFunctionalElement1(__VLS_intrinsics.h1, __VLS_intrinsics.h1)({});
            __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({});
            (__VLS_ctx.current?.seed || __VLS_ctx.seed || '你的创作种子会出现在这里。');
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                ...{ class: "task" },
            });
            /** @type {__VLS_StyleScopedClasses['task']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.b, __VLS_intrinsics.b)({});
            (__VLS_ctx.current?.task?.goal || __VLS_ctx.firstTask);
            __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
            (__VLS_ctx.current?.task?.status_message || '正在创建真实 Agent Task');
            if (__VLS_ctx.current?.adopted_story_core_id) {
                __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
                    ...{ onClick: (__VLS_ctx.draftOpening) },
                    ...{ class: "primary" },
                    disabled: (__VLS_ctx.busy),
                });
                /** @type {__VLS_StyleScopedClasses['primary']} */ ;
                (__VLS_ctx.busy ? '写作者正在准备…' : `生成第一${__VLS_ctx.isNovel ? '章' : '场'}候选`);
            }
        }
        if (__VLS_ctx.error) {
            __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({
                ...{ class: "error" },
            });
            /** @type {__VLS_StyleScopedClasses['error']} */ ;
            (__VLS_ctx.error);
        }
    }
    else if (__VLS_ctx.mode === 'plan') {
        __VLS_asFunctionalElement1(__VLS_intrinsics.article, __VLS_intrinsics.article)({
            ...{ class: "paper planning" },
        });
        /** @type {__VLS_StyleScopedClasses['paper']} */ ;
        /** @type {__VLS_StyleScopedClasses['planning']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.small, __VLS_intrinsics.small)({});
        if (__VLS_ctx.current?.adopted_story_core_id) {
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                ...{ class: "plan-heading" },
            });
            /** @type {__VLS_StyleScopedClasses['plan-heading']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
            __VLS_asFunctionalElement1(__VLS_intrinsics.h1, __VLS_intrinsics.h1)({});
            (__VLS_ctx.current.task?.candidates.find(x => x.id === __VLS_ctx.current?.adopted_story_core_id)?.title);
            __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({});
            (__VLS_ctx.current.task?.candidates.find(x => x.id === __VLS_ctx.current?.adopted_story_core_id)?.logline);
            __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
                ...{ class: (['health', __VLS_ctx.continuity?.health]) },
            });
            /** @type {__VLS_StyleScopedClasses['health']} */ ;
            (__VLS_ctx.continuity?.health === 'stable' ? '连续性稳定' : __VLS_ctx.continuity?.health === 'risk' ? '存在阻断' : '需要关注');
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                ...{ class: "truth" },
            });
            /** @type {__VLS_StyleScopedClasses['truth']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.b, __VLS_intrinsics.b)({});
            __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
            if (__VLS_ctx.continuity) {
                __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                    ...{ class: "control-grid" },
                });
                /** @type {__VLS_StyleScopedClasses['control-grid']} */ ;
                __VLS_asFunctionalElement1(__VLS_intrinsics.section, __VLS_intrinsics.section)({});
                __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                    ...{ class: "section-title" },
                });
                /** @type {__VLS_StyleScopedClasses['section-title']} */ ;
                __VLS_asFunctionalElement1(__VLS_intrinsics.b, __VLS_intrinsics.b)({});
                __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
                (__VLS_ctx.continuity.entities.length);
                for (const [entity] of __VLS_vFor((__VLS_ctx.continuity.entities))) {
                    __VLS_asFunctionalElement1(__VLS_intrinsics.article, __VLS_intrinsics.article)({
                        key: (entity.id),
                        ...{ class: "control-card" },
                    });
                    /** @type {__VLS_StyleScopedClasses['control-card']} */ ;
                    __VLS_asFunctionalElement1(__VLS_intrinsics.b, __VLS_intrinsics.b)({});
                    (entity.name);
                    __VLS_asFunctionalElement1(__VLS_intrinsics.small, __VLS_intrinsics.small)({});
                    (entity.frozen ? '已冻结事实' : '工作状态');
                    (entity.source_label);
                    __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({});
                    (entity.truth.identity);
                    // @ts-ignore
                    [mode, seed, isNovel, isNovel, firstTask, error, error, busy, busy, busy, busy, busy, busy, manuscript, manuscript, current, current, current, current, current, current, current, current, current, adoptOpening, draftOpening, draftOpening, continuity, continuity, continuity, continuity, continuity, continuity,];
                }
                __VLS_asFunctionalElement1(__VLS_intrinsics.section, __VLS_intrinsics.section)({});
                __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                    ...{ class: "section-title" },
                });
                /** @type {__VLS_StyleScopedClasses['section-title']} */ ;
                __VLS_asFunctionalElement1(__VLS_intrinsics.b, __VLS_intrinsics.b)({});
                __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
                (__VLS_ctx.continuity.threads.length);
                for (const [thread] of __VLS_vFor((__VLS_ctx.continuity.threads))) {
                    __VLS_asFunctionalElement1(__VLS_intrinsics.article, __VLS_intrinsics.article)({
                        key: (thread.id),
                        ...{ class: "control-card" },
                    });
                    /** @type {__VLS_StyleScopedClasses['control-card']} */ ;
                    __VLS_asFunctionalElement1(__VLS_intrinsics.b, __VLS_intrinsics.b)({});
                    (thread.title);
                    __VLS_asFunctionalElement1(__VLS_intrinsics.small, __VLS_intrinsics.small)({});
                    (thread.thread_type);
                    (thread.status);
                    __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({});
                    (thread.payoff_target);
                    // @ts-ignore
                    [continuity, continuity,];
                }
            }
        }
        else {
            __VLS_asFunctionalElement1(__VLS_intrinsics.h1, __VLS_intrinsics.h1)({});
            __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({});
        }
    }
    else {
        __VLS_asFunctionalElement1(__VLS_intrinsics.article, __VLS_intrinsics.article)({
            ...{ class: "paper review" },
        });
        /** @type {__VLS_StyleScopedClasses['paper']} */ ;
        /** @type {__VLS_StyleScopedClasses['review']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.small, __VLS_intrinsics.small)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.h1, __VLS_intrinsics.h1)({});
        (__VLS_ctx.current?.task?.status === 'waiting_decision' ? '选择故事生长方向' : '创意团队正在工作');
        __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({
            ...{ class: "status" },
        });
        /** @type {__VLS_StyleScopedClasses['status']} */ ;
        (__VLS_ctx.current?.task?.status_message);
        if (__VLS_ctx.current?.task?.candidates.length) {
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                ...{ class: "candidates" },
            });
            /** @type {__VLS_StyleScopedClasses['candidates']} */ ;
            for (const [c] of __VLS_vFor((__VLS_ctx.current.task.candidates))) {
                __VLS_asFunctionalElement1(__VLS_intrinsics.section, __VLS_intrinsics.section)({
                    key: (c.id),
                    ...{ class: (['candidate', { adopted: c.status === 'adopted' }]) },
                });
                /** @type {__VLS_StyleScopedClasses['adopted']} */ ;
                /** @type {__VLS_StyleScopedClasses['candidate']} */ ;
                __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
                __VLS_asFunctionalElement1(__VLS_intrinsics.small, __VLS_intrinsics.small)({});
                (c.title);
                __VLS_asFunctionalElement1(__VLS_intrinsics.h2, __VLS_intrinsics.h2)({});
                (c.promise);
                __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({});
                (c.logline);
                __VLS_asFunctionalElement1(__VLS_intrinsics.dl, __VLS_intrinsics.dl)({});
                __VLS_asFunctionalElement1(__VLS_intrinsics.dt, __VLS_intrinsics.dt)({});
                __VLS_asFunctionalElement1(__VLS_intrinsics.dd, __VLS_intrinsics.dd)({});
                (c.dramatic_question);
                __VLS_asFunctionalElement1(__VLS_intrinsics.dt, __VLS_intrinsics.dt)({});
                __VLS_asFunctionalElement1(__VLS_intrinsics.dd, __VLS_intrinsics.dd)({});
                (c.conflict);
                __VLS_asFunctionalElement1(__VLS_intrinsics.dt, __VLS_intrinsics.dt)({});
                __VLS_asFunctionalElement1(__VLS_intrinsics.dd, __VLS_intrinsics.dd)({});
                (c.source_strategy);
                if (c.status === 'candidate') {
                    __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!!(__VLS_ctx.screen === 'dashboard'))
                                    throw 0;
                                if (!!(__VLS_ctx.screen === 'create'))
                                    throw 0;
                                if (!!(__VLS_ctx.mode === 'focus'))
                                    throw 0;
                                if (!!(__VLS_ctx.mode === 'plan'))
                                    throw 0;
                                if (!(__VLS_ctx.current?.task?.candidates.length))
                                    throw 0;
                                if (!(c.status === 'candidate'))
                                    throw 0;
                                return (__VLS_ctx.adopt(c));
                                // @ts-ignore
                                [current, current, current, current, adopt,];
                            } },
                        ...{ class: "primary" },
                        disabled: (__VLS_ctx.busy),
                    });
                    /** @type {__VLS_StyleScopedClasses['primary']} */ ;
                }
                else if (c.status === 'adopted') {
                    __VLS_asFunctionalElement1(__VLS_intrinsics.b, __VLS_intrinsics.b)({
                        ...{ class: "adopted-label" },
                    });
                    /** @type {__VLS_StyleScopedClasses['adopted-label']} */ ;
                }
                // @ts-ignore
                [busy,];
            }
        }
        else if (__VLS_ctx.current?.task) {
            __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
                ...{ onClick: (__VLS_ctx.runFirstTask) },
                ...{ class: "primary" },
                disabled: (__VLS_ctx.busy),
            });
            /** @type {__VLS_StyleScopedClasses['primary']} */ ;
            (__VLS_ctx.busy ? 'Agent 正在工作…' : '启动创意导演');
        }
    }
}
if (__VLS_ctx.screen === 'workspace') {
    __VLS_asFunctionalElement1(__VLS_intrinsics.section, __VLS_intrinsics.section)({
        ...{ class: "director-console" },
    });
    /** @type {__VLS_StyleScopedClasses['director-console']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "director-label" },
    });
    /** @type {__VLS_StyleScopedClasses['director-label']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.b, __VLS_intrinsics.b)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
    (__VLS_ctx.directives.filter(x => x.status === 'active').length);
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "scope-switch" },
    });
    /** @type {__VLS_StyleScopedClasses['scope-switch']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.screen === 'workspace'))
                    throw 0;
                return (__VLS_ctx.directiveScope = 'next_task');
                // @ts-ignore
                [screen, busy, busy, current, runFirstTask, directives, directiveScope,];
            } },
        ...{ class: ({ active: __VLS_ctx.directiveScope === 'next_task' }) },
    });
    /** @type {__VLS_StyleScopedClasses['active']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.screen === 'workspace'))
                    throw 0;
                return (__VLS_ctx.directiveScope = 'project_rule');
                // @ts-ignore
                [directiveScope, directiveScope,];
            } },
        ...{ class: ({ active: __VLS_ctx.directiveScope === 'project_rule' }) },
    });
    /** @type {__VLS_StyleScopedClasses['active']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.textarea, __VLS_intrinsics.textarea)({
        ...{ onKeydown: (__VLS_ctx.submitDirective) },
        value: (__VLS_ctx.directiveText),
        rows: "2",
        placeholder: "告诉团队：这次想达到什么、哪里不对、必须保留什么、绝对不要做什么…",
    });
    __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
        ...{ onClick: (__VLS_ctx.submitDirective) },
        ...{ class: "send-directive" },
        disabled: (__VLS_ctx.busy || !__VLS_ctx.directiveText.trim()),
    });
    /** @type {__VLS_StyleScopedClasses['send-directive']} */ ;
    if (__VLS_ctx.directiveNotice) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.small, __VLS_intrinsics.small)({
            ...{ class: "directive-notice" },
        });
        /** @type {__VLS_StyleScopedClasses['directive-notice']} */ ;
        (__VLS_ctx.directiveNotice);
    }
}
// @ts-ignore
[busy, directiveScope, submitDirective, submitDirective, directiveText, directiveText, directiveNotice, directiveNotice,];
const __VLS_export = (await import('vue')).defineComponent({});
export default {};
