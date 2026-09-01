import { http } from './http'
import type {
  ApiSuccess,
  ChatAnswer,
  ChatOperationResult,
  ChatQueryRequest,
  ChatReplayRequest,
  ConversationDetail,
  ConversationSummary,
  PolicyReader,
  RefreshMeta,
  ReplayMeta,
} from '../types/api'

export async function askQuestion(payload: ChatQueryRequest): Promise<ChatAnswer> {
  const response = await http.post<ApiSuccess<ChatAnswer>>('/chat/query', payload)
  return response.data.data
}

export async function replayAnswer(payload: ChatReplayRequest): Promise<ChatOperationResult<ReplayMeta>> {
  const response = await http.post<ApiSuccess<ChatAnswer, ReplayMeta>>('/chat/replay', payload)
  return { answer: response.data.data, meta: response.data.meta! }
}

export async function refreshAnswer(answerId: string): Promise<ChatOperationResult<RefreshMeta>> {
  const response = await http.post<ApiSuccess<ChatAnswer, RefreshMeta>>(`/answers/${answerId}/refresh`)
  return { answer: response.data.data, meta: response.data.meta! }
}

export async function fetchConversations(): Promise<ConversationSummary[]> {
  const response = await http.get<ApiSuccess<ConversationSummary[]>>('/conversations')
  return response.data.data
}

export async function createConversation(title?: string): Promise<{ id: string }> {
  const response = await http.post<ApiSuccess<{ id: string }>>('/conversations', title ? { title } : {})
  return response.data.data
}

export async function fetchConversation(id: string): Promise<ConversationDetail> {
  const response = await http.get<ApiSuccess<ConversationDetail>>(`/conversations/${id}`)
  return response.data.data
}

export async function removeConversation(id: string): Promise<void> {
  await http.delete(`/conversations/${id}`)
}

export async function updateConversation(
  id: string, payload: { title?: string; is_pinned?: boolean },
): Promise<{ id: string; title: string | null; is_pinned: boolean; updated_at: string }> {
  const response = await http.patch<ApiSuccess<{ id: string; title: string | null; is_pinned: boolean; updated_at: string }>>(
    `/conversations/${id}`, payload,
  )
  return response.data.data
}

export async function fetchPolicyReader(versionId: number): Promise<PolicyReader> {
  const response = await http.get<ApiSuccess<PolicyReader>>(`/policies/${versionId}/reader`)
  return response.data.data
}
