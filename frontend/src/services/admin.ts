import { http, rememberCsrfToken } from './http'
import type {
  AdminSession,
  AnalyticsSummary,
  ApiSuccess,
  IndexStatus,
  PolicyReader,
  PolicySummary,
  PolicyVersionSummary,
  FeedbackRecord,
  FeedbackStatus,
  FeedbackType,
  RegressionCase,
  RetestResult,
  SearchTestResult,
} from '../types/api'

export interface PolicyListMeta {
  page: number
  page_size: number
  total: number
  pages: number
}

export interface SearchTestResponse {
  question: string
  knowledge_fingerprint: string
  results: SearchTestResult[]
}

export async function fetchAdminSession(): Promise<AdminSession> {
  const response = await http.get<ApiSuccess<AdminSession>>('/admin/auth/session')
  return response.data.data
}

export async function loginAdmin(username: string, password: string): Promise<AdminSession> {
  const response = await http.post<ApiSuccess<AdminSession>>('/admin/auth/login', { username, password })
  rememberCsrfToken(response.data.data.csrf_token ?? null)
  return response.data.data
}

export async function logoutAdmin(): Promise<void> {
  await http.post('/admin/auth/logout')
  rememberCsrfToken(null)
}

export async function fetchPolicies(): Promise<{ items: PolicySummary[]; meta: PolicyListMeta }> {
  const response = await http.get<ApiSuccess<PolicySummary[], PolicyListMeta>>('/admin/policies', {
    params: { page: 1, page_size: 100 },
  })
  return { items: response.data.data, meta: response.data.meta ?? { page: 1, page_size: 100, total: 0, pages: 0 } }
}

export async function uploadPolicy(form: FormData): Promise<PolicySummary> {
  const response = await http.post<ApiSuccess<PolicySummary>>('/admin/policies', form)
  return response.data.data
}

export async function updatePolicyVersion(
  versionId: number,
  payload: { status?: PolicyVersionSummary['status']; effective_date?: string },
): Promise<PolicyVersionSummary> {
  const response = await http.patch<ApiSuccess<PolicyVersionSummary>>(`/admin/policy-versions/${versionId}`, payload)
  return response.data.data
}

export async function deletePolicyVersion(versionId: number): Promise<void> {
  await http.delete(`/admin/policy-versions/${versionId}`)
}

export async function fetchAdminPolicyReader(versionId: number): Promise<PolicyReader> {
  const response = await http.get<ApiSuccess<PolicyReader>>(`/policies/${versionId}/reader`)
  return response.data.data
}

export async function fetchIndexStatus(): Promise<IndexStatus> {
  const response = await http.get<ApiSuccess<IndexStatus>>('/admin/index/status')
  return response.data.data
}

export async function rebuildIndex(): Promise<IndexStatus> {
  const response = await http.post<ApiSuccess<IndexStatus>>('/admin/index/rebuild')
  return response.data.data
}

export async function testSearch(question: string): Promise<SearchTestResponse> {
  const response = await http.post<ApiSuccess<SearchTestResponse>>('/admin/search/test', { question })
  return response.data.data
}

export interface AdminFeedbackFilters {
  status?: FeedbackStatus | ''
  feedback_type?: FeedbackType | ''
  policy_id?: number | ''
  date_from?: string
  date_to?: string
}

export async function fetchAdminFeedback(filters: AdminFeedbackFilters = {}): Promise<FeedbackRecord[]> {
  const response = await http.get<ApiSuccess<FeedbackRecord[]>>('/admin/feedback', { params: filters })
  return response.data.data
}

export async function updateFeedbackStatus(
  id: string,
  action: 'start_processing' | 'return_open' | 'resolve' | 'reject',
  note?: string,
): Promise<FeedbackRecord> {
  const response = await http.patch<ApiSuccess<FeedbackRecord>>(`/admin/feedback/${id}`, { action, note })
  return response.data.data
}

export async function retestFeedback(id: string): Promise<RetestResult> {
  const response = await http.post<ApiSuccess<RetestResult>>(`/admin/feedback/${id}/retest`)
  return response.data.data
}

export async function createRegressionCase(id: string): Promise<RegressionCase> {
  const response = await http.post<ApiSuccess<RegressionCase>>(`/admin/feedback/${id}/regression-case`)
  return response.data.data
}

export async function fetchRegressionCases(): Promise<RegressionCase[]> {
  const response = await http.get<ApiSuccess<RegressionCase[]>>('/admin/regression-cases')
  return response.data.data
}

export async function fetchAnalytics(params: AdminFeedbackFilters = {}): Promise<AnalyticsSummary> {
  const response = await http.get<ApiSuccess<AnalyticsSummary>>('/admin/analytics', {
    params: {
      date_from: params.date_from,
      date_to: params.date_to,
      policy_id: params.policy_id,
      feedback_status: params.status,
    },
  })
  return response.data.data
}
