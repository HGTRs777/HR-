import { http, rememberCsrfToken } from './http'
import type {
  AdminSession,
  AnalyticsSummary,
  ApiSuccess,
  ClauseReferences,
  IndexStatus,
  PolicyReader,
  PolicySummary,
  PolicyVersionSummary,
  PolicyGapScan,
  PolicyIssue,
  PolicyBriefing,
  PolicyInsights,
  PolicySummaryStats,
  PolicyIssueRetest,
  PolicyIssueSource,
  PolicyIssueStatus,
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

export async function loginAdmin(username: string, password: string, challengeId: string, sliderPosition: number): Promise<AdminSession> {
  const response = await http.post<ApiSuccess<AdminSession>>('/admin/auth/login', {
    username,
    password,
    challenge_id: challengeId,
    slider_position: sliderPosition,
  })
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

export async function fetchClauseReferences(clauseId: number): Promise<ClauseReferences> {
  const response = await http.get<ApiSuccess<ClauseReferences>>(`/admin/clauses/${clauseId}/references`)
  return response.data.data
}

export async function fetchIndexStatus(): Promise<IndexStatus> {
  const response = await http.get<ApiSuccess<IndexStatus>>('/admin/index/status')
  return response.data.data
}

export async function rebuildIndex(): Promise<IndexStatus> {
  const response = await http.post<ApiSuccess<IndexStatus>>('/admin/index/rebuild', undefined, { timeout: 180_000 })
  return response.data.data
}

export async function testSearch(question: string): Promise<SearchTestResponse> {
  const response = await http.post<ApiSuccess<SearchTestResponse>>('/admin/search/test', { question }, { timeout: 60_000 })
  return response.data.data
}

export interface AdminFeedbackFilters {
  status?: FeedbackStatus | ''
  feedback_type?: FeedbackType | ''
  policy_id?: number | ''
  date_from?: string
  date_to?: string
  answer_status?: string
  question_type?: string
  only_missed?: boolean
  only_negative?: boolean
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
      answer_status: params.answer_status,
      question_type: params.question_type,
      only_missed: params.only_missed || undefined,
      only_negative: params.only_negative || undefined,
    },
  })
  return response.data.data
}

export async function fetchPolicySummary(): Promise<PolicySummaryStats> {
  const response = await http.get<ApiSuccess<PolicySummaryStats>>('/admin/policy-summary')
  return response.data.data
}

export async function fetchPolicyBriefing(range: 'today' | 'week'): Promise<PolicyBriefing> {
  const response = await http.get<ApiSuccess<PolicyBriefing>>('/admin/policy-briefing', { params: { range } })
  return response.data.data
}

export async function fetchPolicyInsights(days: 7 | 30): Promise<PolicyInsights> {
  const response = await http.get<ApiSuccess<PolicyInsights>>('/admin/policy-insights', { params: { days } })
  return response.data.data
}

export async function fetchLatestPolicyGapScan(): Promise<PolicyGapScan | null> {
  const response = await http.get<ApiSuccess<PolicyGapScan | null>>('/admin/policy-gaps/latest')
  return response.data.data
}

export async function runPolicyGapScan(): Promise<PolicyGapScan> {
  const response = await http.post<ApiSuccess<PolicyGapScan>>('/admin/policy-gaps/scan')
  return response.data.data
}

export interface PolicyIssueFilters {
  source?: PolicyIssueSource | ''
  severity?: PolicyIssue['severity'] | ''
  status?: PolicyIssueStatus | ''
}

export async function fetchPolicyIssues(filters: PolicyIssueFilters = {}): Promise<PolicyIssue[]> {
  const response = await http.get<ApiSuccess<PolicyIssue[]>>('/admin/policy-issues', { params: filters })
  return response.data.data
}

export async function createPolicyIssueFromInsight(payload: {
  question: string
  category: PolicyIssue['category']
  occurrences: number
}): Promise<{ issue: PolicyIssue; created: boolean }> {
  const response = await http.post<ApiSuccess<{ issue: PolicyIssue; created: boolean }>>('/admin/policy-issues', payload)
  return response.data.data
}

export async function updatePolicyIssue(
  id: number, action: 'start_processing' | 'add_note' | 'resolve' | 'reopen', note?: string,
): Promise<PolicyIssue> {
  const response = await http.patch<ApiSuccess<PolicyIssue>>(`/admin/policy-issues/${id}`, { action, note })
  return response.data.data
}

export async function retestPolicyIssue(id: number): Promise<PolicyIssueRetest> {
  const response = await http.post<ApiSuccess<PolicyIssueRetest>>(`/admin/policy-issues/${id}/retest`, undefined, { timeout: 60_000 })
  return response.data.data
}
