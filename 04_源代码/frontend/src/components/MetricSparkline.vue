<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ values: number[]; color?: string }>()
const points = computed(() => {
  if (!props.values.length) return ''
  const min = Math.min(...props.values)
  const max = Math.max(...props.values)
  const range = Math.max(max - min, 1)
  return props.values.map((value, index) => {
    const x = props.values.length === 1 ? 50 : index * (100 / (props.values.length - 1))
    const y = 27 - ((value - min) / range) * 22
    return `${x},${y}`
  }).join(' ')
})
</script>

<template>
  <svg class="metric-sparkline" viewBox="0 0 100 32" preserveAspectRatio="none" aria-hidden="true">
    <polyline v-if="points" :points="points" fill="none" :stroke="color || '#176b55'" stroke-width="2.5" vector-effect="non-scaling-stroke" />
  </svg>
</template>
