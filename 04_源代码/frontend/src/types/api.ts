export interface ApiSuccess<T, M = Record<string, unknown>> {
  ok: true
  data: T
  meta?: M
}

export interface ApiFailure {
  ok: false
  error: {
    code: string
    message: string
    request_id?: string
    details?: unknown
  }
}

export type ApiEnvelope<T, M = Record<string, unknown>> = ApiSuccess<T, M> | ApiFailure

export interface HealthStatus {
  status: 'ok' | 'degraded'
  services: {
    api: 'ok' | 'error'
    database: 'ok' | 'error'
    deepseek: 'configured' | 'not_configured' | 'error'
    embedding_index: 'ready' | 'not_built' | 'stale' | 'error'
  }
  version: string
}

export type AnswerStatus = 'answer' | 'clarification' | 'refusal' | 'degraded'
export type AnswerDecision = 'allowed' | 'denied' | 'conditional' | 'informational'
export type QuestionType = 'eligibility' | 'deadline' | 'duration' | 'quota' | 'procedure' | 'materials' | 'approver' | 'destination' | 'condition' | 'status' | 'definition' | 'reason' | 'policy_lookup' | 'general'

export interface ScenarioState {
  employee_status?: string
  tenure_years?: number
  matter_type?: string
  duration_days?: number
  [key: string]: string | number | boolean | null | undefined
}

export interface ClarificationOption {
  value: string | number | boolean
  label: string
}

export interface ClarificationRequest {
  slot: string
  question: string
  options: ClarificationOption[]
}

export interface ScenarioFormField {
  field: string
  label: string
  type: 'select' | 'number' | 'boolean'
  required: boolean
  answered: boolean
  value?: string | number | boolean | null
  min?: number
  max?: number
  step?: number
  unit?: string
  constraint_hint?: string
  options?: ClarificationOption[]
}

export interface EmployeeContextField {
  field: string
  label: string
  value: string | number | boolean | null
  value_label: string
  source: 'employee_profile' | 'derived_from_hire_date'
}

export interface Evidence {
  id: string
  clause_id: number
  stable_anchor: string
  policy_id: number
  policy_code: string
  policy_title: string
  policy_version_id: number
  policy_version: string
  effective_date: string
  section_path: string
  clause_number: string | null
  page_number: number | null
  quote: string
  rank: number
  vector_score?: number
  bm25_score?: number
  rrf_score?: number
}

export interface Claim {
  id: string
  position: number
  text: string
  evidence_ids: string[]
  evidence_validated: boolean
}

export interface ActionCardStep {
  id?: string
  title: string
  description: string
  evidence_ids: string[]
}

export interface ChecklistTask extends ActionCardStep {
  id: string
  category: 'action' | 'material' | string
}

export interface ProcessFlowStep {
  id: string
  label: string
  detail: string
  evidence_ids: string[]
  person_configured?: boolean
}

export interface ActionCard {
  conclusion?: string
  applicable_conditions: string[]
  tasks?: ChecklistTask[]
  process_flow?: ProcessFlowStep[]
  estimated_completion?: string | null
  generation_source?: 'structured_template' | string
  basis_evidence_ids?: string[]
  timeline: ActionCardStep[]
  materials: ActionCardStep[]
  cautions: ActionCardStep[]
  next_steps?: Array<{ text: string; evidence_ids: string[] }>
}

export interface ChatQueryRequest {
  conversation_id?: string
  question: string
  scenario?: ScenarioState
}

export interface ChatReplayRequest {
  answer_id: string
  scenario: ScenarioState
}

export interface ChatAnswer {
  answer_id: string
  conversation_id: string
  status: AnswerStatus
  decision: AnswerDecision
  question_type: QuestionType
  answer_focus: string
  primary_answer: string
  conclusion: '可以' | '不可以' | '需要' | '不需要' | '符合' | '不符合' | '条件不足，暂时无法判断' | string
  decision_statement: string
  summary?: string
  claims: Claim[]
  reason_title?: string | null
  reason_items?: string[]
  chat_answer?: string
  next_steps: Array<{ text: string; evidence_ids: string[] }>
  missing_conditions: string[]
  scenario: ScenarioState
  employee_context: {
    known: EmployeeContextField[]
    missing: EmployeeContextField[]
  }
  clarification?: ClarificationRequest
  action_card: ActionCard
  checklist?: ActionCard
  scenario_form?: ScenarioFormField[]
  source_answer_id?: string | null
  generation_kind: 'query' | 'replay' | 'refresh'
  evidence: Evidence[]
  evidence_coverage: number
  knowledge_fingerprint?: string
  stale: boolean
  policy_updates?: PolicyUpdate[]
  degraded: boolean
  degraded_reason: string | null
  created_at: string
}

export interface PolicyUpdate {
  policy_id: number
  policy_title: string
  previous_version_id: number
  previous_version: string
  previous_effective_date: string
  current_version_id: number
  current_version: string
  current_effective_date: string
}

export interface ScenarioChange {
  field: string
  label: string
  before: string | number | boolean | null
  after: string | number | boolean | null
  before_label: string
  after_label: string
}

export interface ReplayMeta {
  previous_answer_id: string
  scenario_changes: ScenarioChange[]
  recalculation_message: string
}

export interface RefreshMeta {
  previous_answer_id: string
  previous_knowledge_fingerprint?: string | null
  current_knowledge_fingerprint?: string | null
}

export interface ChatOperationResult<M> {
  answer: ChatAnswer
  meta: M
}

export interface ConversationSummary {
  id: string
  title: string | null
  is_pinned: boolean
  scenario: ScenarioState
  message_count: number
  answer_count: number
  has_stale_answers: boolean
  created_at: string
  updated_at: string
}

export interface ConversationMessage {
  id: number
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at: string
}

export interface ConversationDetail {
  id: string
  title: string | null
  is_pinned: boolean
  scenario: ScenarioState
  messages: ConversationMessage[]
  answers: ChatAnswer[]
  created_at: string
  updated_at: string
}

export interface PolicySummary {
  id: number
  code: string
  title: string
  category: string
  active_version_id: number | null
  version_count: number
  created_at: string
  updated_at: string
  versions?: PolicyVersionSummary[]
}

export interface PolicyVersionSummary {
  id: number
  version: string
  effective_date: string
  status: 'draft' | 'active' | 'inactive'
  file_name: string
  mime_type: string
  size_bytes: number
  file_sha256: string
  parsed_at: string | null
  parse_error: string | null
  clause_count: number
  created_at: string
}

export interface AdminSession {
  authenticated: boolean
  admin: { id: number; username: string; display_name: string } | null
  csrf_token?: string
}

export interface EmployeeSession {
  authenticated: boolean
  employee: {
    id: number
    username: string
    display_name: string
    department: string | null
    job_title: string | null
    hire_date: string | null
    employee_status: string | null
    tenure_years: number | null
    direct_manager: string | null
    hrbp: string | null
    annual_leave_entitlement: number | null
    annual_leave_balance: number | null
  } | null
}

export interface HumanChallenge {
  challenge_id: string
  prompt: string
  target_position: number
  pattern_seed: number
  expires_in: number
}

export interface PolicyClause {
  clause_id: number
  stable_anchor: string
  section_path: string
  clause_number: string | null
  page_number: number | null
  paragraph_index: number | null
  text: string
}

export interface PolicyReader {
  policy_id: number
  policy_code: string
  policy_title: string
  category: string
  policy_version_id: number
  policy_version: string
  effective_date: string
  status: 'draft' | 'active' | 'inactive'
  clauses: PolicyClause[]
}

export interface ClauseReferences {
  clause_id: number
  total_references: number
  question_count: number
  questions: Array<{
    question: string
    reference_count: number
    average_rank: number | null
    last_referenced_at: string | null
  }>
}

export interface IndexStatus {
  status: 'ready' | 'not_built' | 'stale'
  fingerprint: string | null
  current_knowledge_fingerprint: string
  stale: boolean
  clause_count: number
  active_clause_count: number
  embedding_model: string
  chunker_version: string
  built_at: string | null
  error: string | null
}

export interface SearchTestResult {
  rank: number
  clause_id: number
  stable_anchor: string
  policy_id: number
  policy_code: string
  policy_title: string
  policy_version_id: number
  policy_version: string
  effective_date: string
  section_path: string
  clause_number: string | null
  page_number: number | null
  text: string
  vector_score: number
  vector_rank: number
  bm25_score: number
  bm25_rank: number
  rrf_score: number
}

export type FeedbackStatus = 'open' | 'processing' | 'resolved' | 'rejected'

export type FeedbackType = 'helpful' | 'wrong_answer' | 'missing_policy' | 'outdated_policy' | 'unclear' | 'missing_process' | 'suggestion'

export interface FeedbackEvent {
  id: number
  actor_type: 'employee' | 'admin'
  action: string
  note: string | null
  event_data: Record<string, unknown>
  created_at: string
}

export interface RetestResult {
  passed: boolean
  question: string
  knowledge_fingerprint: string
  expected_anchors: string[]
  retrieved_anchors: string[]
  top_score: number | null
  run_at: string
}

export interface FeedbackRecord {
  id: string
  answer_id?: string | null
  conversation_id?: string | null
  primary_policy_id?: number | null
  submitter_name?: string | null
  is_anonymous: boolean
  feedback_type: FeedbackType
  content: string
  auto_category?: string | null
  status: FeedbackStatus
  events: FeedbackEvent[]
  last_retest?: RetestResult | null
  answer_snapshot?: ChatAnswer & { question: string; normalized_question?: string | null }
  created_at: string
  updated_at: string
}

export interface FeedbackCreateRequest {
  answer_id: string
  feedback_type: FeedbackType
  content: string
  is_anonymous: boolean
  submitter_name?: string | null
}

export interface RegressionCase {
  id: number
  feedback_id: string | null
  question: string
  scenario: ScenarioState
  expected_evidence: Array<{ stable_anchor: string; policy_code?: string; policy_version?: string }>
  status: 'pending' | 'passed' | 'failed'
  last_run_at: string | null
  last_result: RetestResult | Record<string, unknown>
  created_at: string
}

export interface AnalyticsSummary {
  query_count: number
  hit_rate: number
  trusted_hit_rate: number
  finalized_query_count: number
  refusal_rate: number
  degraded_rate: number
  clarification_rate: number
  average_latency_ms: number
  feedback_count: number
  open_feedback_count: number
  regression_case_count: number
  popular_questions: AnalyticsQuestion[]
  missed_questions: AnalyticsQuestion[]
  feedback_by_category: Array<{ category: string; count: number }>
  feedback_by_status: Array<{ status: FeedbackStatus; count: number }>
  daily_queries: Array<{ date: string; count: number }>
  daily_quality: Array<{
    date: string
    query_count: number
    hit_rate: number
    clarification_rate: number
    refusal_rate: number
    average_latency_ms: number | null
  }>
  period_comparison: Record<'query_count' | 'hit_rate' | 'trusted_hit_rate' | 'refusal_rate' | 'clarification_rate' | 'average_latency_ms' | 'negative_feedback_count', number | null>
  policy_hits: Array<{ policy_id: number; policy_title: string; count: number }>
  filters: {
    date_from: string | null; date_to: string | null; policy_id: number | null; feedback_status: FeedbackStatus | null
    answer_status: string | null; question_type: string | null; only_missed: boolean; only_negative: boolean
  }
}

export interface AnalyticsQuestion {
  question: string
  count: number
  status_counts: Record<string, number>
  latest_status: string | null
  last_seen_at: string | null
  average_top_score: number | null
  average_retrieval_latency_ms: number | null
  average_total_latency_ms: number | null
  policies: Array<{ policy_id: number; policy_title: string }>
  feedback_count: number
  latest_answer: string | null
  ever_missed: boolean
  reason: string | null
  issue_category: PolicyGapIssue['category'] | null
}

export interface PolicyGapIssue {
  id: number
  category: 'missing_policy' | 'unclear_rule' | 'conflict' | 'outdated' | 'unanswered' | 'accuracy'
  severity: 'high' | 'medium' | 'low'
  title: string
  description: string
  suggested_action: string
  occurrences: number
  evidence: Array<Record<string, unknown>>
  scan_id?: string | null
  sources?: PolicyIssueSource[]
  status?: PolicyIssueStatus
  origin_question?: string | null
  processing_note?: string | null
  last_retest?: PolicyIssueRetest | Record<string, never>
  history?: Array<Record<string, unknown>>
  created_at?: string
  last_seen_at?: string
  resolved_at?: string | null
}

export type PolicyIssueSource = 'ai_scan' | 'qa_insight' | 'employee_feedback' | 'manual'
export type PolicyIssueStatus = 'pending' | 'processing' | 'resolved'

export interface PolicyIssueRetest {
  passed: boolean
  question: string
  previous_status: string
  current_status: string
  knowledge_fingerprint: string
  top_score: number | null
  citations: SearchTestResult[]
  run_at: string
}

export interface PolicyIssue extends PolicyGapIssue {
  sources: PolicyIssueSource[]
  status: PolicyIssueStatus
  origin_question: string | null
  processing_note: string | null
  last_retest: PolicyIssueRetest | Record<string, never>
  history: Array<Record<string, unknown>>
  created_at: string
  last_seen_at: string
  resolved_at: string | null
  policies: Array<{ policy_id: number; policy_title: string }>
  recent_consultations: number
  is_recurring: boolean
  affects_handling: boolean
  open_days: number
  priority_score: number
}

export interface PolicySummaryStats {
  generated_at: string
  pending_issues: number
  severity_counts: Record<'high' | 'medium' | 'low', number>
  new_this_week: number
  new_issue_ids: number[]
  weak_policy_count: number
  weak_policy_ids: number[]
  high_previous_week: number | null
  high_week_change: number | null
}

export interface PolicyBriefing {
  range: 'today' | 'week'
  range_label: '今日' | '本周'
  generated_at: string
  period: { start: string; end: string }
  summary: PolicySummaryStats
  overview: {
    consultations: number
    new_issues: number
    pending_issues: number
    resolved_issues: number
    high_pending_issues: number
  }
  priority_issues: Array<{
    id: number
    severity: PolicyIssue['severity']
    status: PolicyIssueStatus
    title: string
    consultations: number
    previous_period_consultations: number
    policies: Array<{ policy_id: number; policy_title: string }>
  }>
  concern_categories: Array<{ category: string; count: number; share: number; previous_count: number; change: number }>
  weak_policies: Array<{
    policy_id: number
    policy_title: string
    category: string
    unresolved_count: number
    high_count: number
    consultations: number
    issue_ids: number[]
  }>
  changes: {
    consultations: { current: number; previous: number; change: number }
    new_issues: { current: number; previous: number; change: number }
    resolved_issues: { current: number; previous: number; change: number }
    leading_category: { category: string; count: number; share: number; previous_count: number; change: number } | null
  }
}

export interface PolicyInsights {
  generated_at: string
  days: 7 | 30
  week: {
    consultations: number
    previous_consultations: number
    consultation_change_rate: number | null
    pending_issues: number
    severity_counts: Record<'high' | 'medium' | 'low', number>
    new_issues: number
    new_issue_ids: number[]
    new_issue_categories: Array<{ category: string; count: number }>
    resolved_issues: number
    resolved_issue_ids: number[]
    average_resolution_hours: number | null
  }
  daily_trend: Array<{
    date: string
    consultations: number
    new_issues: number
    leading_category: string | null
  }>
  attention_changes: Array<{
    category: string
    current: number
    previous: number
    change_rate: number | null
    policy_ids: number[]
    questions: Array<{ question: string; count: number }>
  }>
  weak_policies: Array<{
    policy_id: number
    policy_title: string
    category: string
    pending_count: number
    severity_counts: Record<'high' | 'medium' | 'low', number>
    consultations: number
    issue_ids: number[]
  }>
}

export interface PolicyGapScan {
  id: string
  trigger_type: 'scheduled' | 'manual'
  status: 'running' | 'completed' | 'failed'
  summary: string | null
  query_count: number
  policy_count: number
  model_name: string | null
  error_message: string | null
  started_at: string
  completed_at: string | null
  issues: PolicyGapIssue[]
}
