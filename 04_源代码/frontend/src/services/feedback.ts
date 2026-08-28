import { http } from './http'
import type { ApiSuccess, FeedbackCreateRequest, FeedbackRecord } from '../types/api'

export async function submitFeedback(payload: FeedbackCreateRequest): Promise<FeedbackRecord> {
  const response = await http.post<ApiSuccess<FeedbackRecord>>('/feedback', payload)
  return response.data.data
}

export async function fetchMyFeedback(): Promise<FeedbackRecord[]> {
  const response = await http.get<ApiSuccess<FeedbackRecord[]>>('/feedback')
  return response.data.data
}

export async function fetchFeedbackDetail(id: string): Promise<FeedbackRecord> {
  const response = await http.get<ApiSuccess<FeedbackRecord>>(`/feedback/${id}`)
  return response.data.data
}
