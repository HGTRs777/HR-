import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'

import type { ApiFailure, ApiSuccess } from '../types/api'

const baseURL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:5000/api/v1'
let csrfToken: string | null = null
const clientSessionKey = 'hr-policy-client-session-id'

function getClientSessionId(): string {
  const existing = localStorage.getItem(clientSessionKey)
  if (existing) return existing
  const created = crypto.randomUUID()
  localStorage.setItem(clientSessionKey, created)
  return created
}

export class ApiClientError extends Error {
  readonly code: string
  readonly requestId?: string
  readonly details?: unknown

  constructor(failure: ApiFailure['error']) {
    super(failure.message)
    this.name = 'ApiClientError'
    this.code = failure.code
    this.requestId = failure.request_id
    this.details = failure.details
  }
}

export const http = axios.create({
  baseURL,
  timeout: 30_000,
  withCredentials: true,
  headers: { Accept: 'application/json' },
})

async function getCsrfToken(): Promise<string> {
  if (csrfToken) return csrfToken
  const response = await axios.get<ApiSuccess<{ csrf_token: string }>>(`${baseURL}/admin/auth/csrf`, {
    withCredentials: true,
  })
  csrfToken = response.data.data.csrf_token
  return csrfToken
}

export function rememberCsrfToken(token: string | null): void {
  csrfToken = token
}

http.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
  config.headers.set('X-Client-Session-ID', getClientSessionId())
  const method = config.method?.toUpperCase() ?? 'GET'
  const isAdminMutation =
    typeof config.url === 'string' &&
    config.url.startsWith('/admin/') &&
    !['GET', 'HEAD', 'OPTIONS'].includes(method)
  if (isAdminMutation) {
    config.headers.set('X-CSRF-Token', await getCsrfToken())
  }
  return config
})

http.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiFailure>) => {
    const failure = error.response?.data
    if (failure && failure.ok === false) {
      return Promise.reject(new ApiClientError(failure.error))
    }
    return Promise.reject(error)
  },
)
