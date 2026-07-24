<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'

import AppShell from '../components/AppShell.vue'
import { creativeRoleLabel } from '../creativeRoles'
import { useAgentTeamStore } from '../stores/agentTeam'

const route = useRoute()
const team = useAgentTeamStore()
const projectId = computed(() => String(route.params.projectId))
const availableModels = computed(() => team.models.filter((model) => model.available))
onMounted(() => void team.load(projectId.value))
</script>

<template>
  <AppShell title="创作团队" eyebrow="项目角色配置">
    <section class="team-intro"><div><h2>让每位创作伙伴形成适合这个项目的工作方式。</h2><p>名称、工作风格和模型选择只作用于当前项目，并从下一次协作开始生效。</p></div><RouterLink :to="`/projects/${projectId}`" class="secondary link-button">返回创作现场</RouterLink></section>
    <div class="agent-team-grid">
      <article v-for="member in team.members" :key="member.role_key" class="agent-config-card">
        <header><span>{{ member.role_key.slice(0, 1).toUpperCase() }}</span><div><p class="eyebrow">{{ member.system_name }} · Agent</p><h2>{{ member.custom_name || creativeRoleLabel(member.role_key, member.system_name) }}</h2></div></header>
        <label>项目内称呼<input v-model="member.custom_name" :placeholder="creativeRoleLabel(member.role_key, member.system_name)" maxlength="80" /></label>
        <label>系统 Soul<textarea :value="member.soul_base" readonly /></label>
        <label>Soul 微调<textarea v-model="member.soul_override" maxlength="2000" placeholder="补充这个项目特有的工作原则；不会覆盖系统 Soul。" /></label>
        <label>运行模型<select v-model="member.model_id"><option v-for="model in availableModels" :key="model.id" :value="model.id" data-i18n-skip>{{ model.display_name }} · {{ model.provider_name }}</option></select></label>
        <footer><button class="text-button" :disabled="team.busy === member.role_key" @click="team.reset(projectId, member.role_key)">恢复默认</button><button class="primary" :disabled="team.busy === member.role_key" @click="team.save(projectId, member)">{{ team.busy === member.role_key ? '保存中…' : '保存，下次运行生效' }}</button></footer>
      </article>
    </div>
  </AppShell>
</template>
