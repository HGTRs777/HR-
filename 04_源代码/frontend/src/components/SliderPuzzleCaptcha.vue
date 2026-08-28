<script setup lang="ts">
import { computed } from 'vue'

import type { HumanChallenge } from '../types/api'

const props = defineProps<{
  challenge: HumanChallenge
  modelValue: number | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: number]
  refresh: []
}>()

const position = computed(() => props.modelValue ?? 0)
const aligned = computed(() => Math.abs(position.value - props.challenge.target_position) <= 3)
const stageStyle = computed(() => ({ '--puzzle-hue': `${props.challenge.pattern_seed}deg` }))
const targetStyle = computed(() => ({ left: `calc(${props.challenge.target_position}% - 23px)` }))
const pieceStyle = computed(() => ({ left: `calc(${position.value}% - 23px)` }))

function updatePosition(event: Event): void {
  emit('update:modelValue', Number((event.target as HTMLInputElement).value))
}
</script>

<template>
  <div class="slider-puzzle" :class="{ verified: aligned }">
    <div class="puzzle-heading">
      <span>{{ challenge.prompt }}</span>
      <button type="button" @click="emit('refresh')">换一张</button>
    </div>
    <div class="puzzle-stage" :style="stageStyle" aria-hidden="true">
      <span class="puzzle-landmark landmark-one"></span>
      <span class="puzzle-landmark landmark-two"></span>
      <span class="puzzle-target" :style="targetStyle"></span>
      <span class="puzzle-piece" :style="pieceStyle"><i></i></span>
    </div>
    <label class="puzzle-slider-label">
      <span>{{ aligned ? '验证通过' : '按住滑块向右拖动' }}</span>
      <input
        type="range"
        min="0"
        max="100"
        step="1"
        :value="position"
        aria-label="滑动拼图位置"
        :aria-valuetext="aligned ? '拼图已对齐，验证通过' : `当前位置 ${position}`"
        @input="updatePosition"
      />
    </label>
  </div>
</template>
