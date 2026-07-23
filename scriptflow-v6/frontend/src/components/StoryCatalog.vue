<script setup lang="ts">
export type StoryCatalogUnit = {
  id: number
  title: string
  status: string
}

export type StoryCatalogGroup = {
  id: number
  title: string
  units: StoryCatalogUnit[]
}

defineProps<{
  groups: StoryCatalogGroup[]
  selectedUnitId: number | null
  busy: boolean
  unitLabel: string
}>()

defineEmits<{
  select: [unit: StoryCatalogUnit]
  add: [group: StoryCatalogGroup]
  move: [group: StoryCatalogGroup, unit: StoryCatalogUnit, direction: -1 | 1]
}>()
</script>

<template>
  <section v-for="group in groups" :key="group.id" class="story-group">
    <div class="story-group-head">
      <b>{{ group.title }}</b>
      <button
        :aria-label="`在${group.title}新增${unitLabel}`"
        :disabled="busy"
        @click="$emit('add', group)"
      >＋</button>
    </div>
    <div
      v-for="(unit, index) in group.units"
      :key="unit.id"
      :class="['story-unit-row', { active: selectedUnitId === unit.id }]"
    >
      <button class="tree" @click="$emit('select', unit)">
        <span>{{ unit.title }}</span>
        <small>{{ unit.status === 'planned' ? '待规划' : unit.status }}</small>
      </button>
      <div class="story-order">
        <button
          :aria-label="`上移${unit.title}`"
          :disabled="busy || index === 0"
          @click="$emit('move', group, unit, -1)"
        >↑</button>
        <button
          :aria-label="`下移${unit.title}`"
          :disabled="busy || index === group.units.length - 1"
          @click="$emit('move', group, unit, 1)"
        >↓</button>
      </div>
    </div>
  </section>
</template>
