<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'

const props = withDefaults(defineProps<{ value: number; decimals?: number }>(), { decimals: 0 })
const displayed = ref(import.meta.env.MODE === 'test' ? props.value : 0)
let frame = 0

function animate(next: number): void {
  cancelAnimationFrame(frame)
  if (import.meta.env.MODE === 'test') {
    displayed.value = next
    return
  }
  if (typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches) {
    displayed.value = next
    return
  }
  const startValue = displayed.value
  const startedAt = performance.now()
  const duration = 520
  const tick = (now: number) => {
    const progress = Math.min(1, (now - startedAt) / duration)
    const eased = 1 - Math.pow(1 - progress, 3)
    displayed.value = startValue + (next - startValue) * eased
    if (progress < 1) frame = requestAnimationFrame(tick)
  }
  frame = requestAnimationFrame(tick)
}

watch(() => props.value, animate, { immediate: true })
onBeforeUnmount(() => cancelAnimationFrame(frame))
</script>

<template>{{ displayed.toFixed(decimals) }}</template>
