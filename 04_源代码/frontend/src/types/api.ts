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
  title: string
  description: string
  evidence_ids: string[]
}

export interface ActionCard {
  conclusion?: string
  applicable_conditions: string[]
  timeline: ActionCardStep[]
  materials: ActionCardStep[]
  cautions: ActionCardStep[]
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
  summary?: string
  claims: Claim[]
  scenario: ScenarioState
  clarification?: ClarificationRequest
  action_card: ActionCard
  source_answer_id?: string | null
  generation_kind: 'query' | 'replay' | 'refresh'
  evidence: Evidence[]
  evidence_coverage: number
  knowledge_fingerprint?: string
  stale: boolean
  degraded: boolean
  degraded_reason: string | null
  created_at: string
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
  admin: { id: number; username: string } | null
  csrf_token?: string
}

export interface EmployeeSession {
  authenticated: boolean
  employee: { id: number; username: string; display_name: string; department: string } | null
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

export type FeedbackType = 'wrong_answer' | 'missing_policy' | 'outdated_policy' | 'unclear' | 'suggestion'

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
  refusal_rate: number
  degraded_rate: number
  clarification_rate: number
  average_latency_ms: number
  feedback_count: number
  open_feedback_count: number
  regression_case_count: number
  popular_questions: Array<{ question: string; count: number }>
  missed_questions: Array<{ question: string; count: number }>
  feedback_by_category: Array<{ category: string; count: number }>
  feedback_by_status: Array<{ status: FeedbackStatus; count: number }>
  daily_queries: Array<{ date: string; count: number }>
  policy_hits: Array<{ policy_id: number; policy_title: string; count: number }>
  filters: { date_from: string | null; date_to: string | null; policy_id: number | null; feedback_status: FeedbackStatus | null }
}
