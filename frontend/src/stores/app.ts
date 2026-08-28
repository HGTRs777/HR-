import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { fetchHealth } from '../services/health'
import type { HealthStatus } from '../types/api'

export const useAppStore = defineStore('app', () => {
  const health = ref<HealthStatus | null>(null)
  const healthError = ref<string | null>(null)
  const isLoadingHealth = ref(false)

  const healthLabel = computed(() => {
    if (isLoadingHealth.value) return '服务检查中'
    if (healthError.value) return '后端未连接'
    if (!health.value) return '状态未知'
    if (health.value.status === 'degraded') return '服务降级'
    return '服务正常'
  })

  const healthTagType = computed<'success' | 'warning' | 'danger' | 'info'>(() => {
    if (healthError.value) return 'danger'
    if (!health.value || isLoadingHealth.value) return 'info'
    return health.value.status === 'ok' ? 'success' : 'warning'
  })

  async function loadHealth(): Promise<void> {
    isLoadingHealth.value = true
    healthError.value = null
    try {
      health.value = await fetchHealth()
    } catch (error) {
      healthError.value = error instanceof Error ? error.message : '无法连接后端服务'
    } finally {
      isLoadingHealth.value = false
    }
  }

  return {
    health,
    healthError,
    isLoadingHealth,
    healthLabel,
    healthTagType,
    loadHealth,
  }
})

