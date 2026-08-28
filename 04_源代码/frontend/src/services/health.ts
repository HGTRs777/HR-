import { http } from './http'
import type { ApiSuccess, HealthStatus } from '../types/api'

export async function fetchHealth(): Promise<HealthStatus> {
  const response = await http.get<ApiSuccess<HealthStatus>>('/health')
  return response.data.data
}

