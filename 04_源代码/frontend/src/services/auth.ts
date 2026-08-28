import { http } from './http'
import type { ApiSuccess, EmployeeSession, HumanChallenge } from '../types/api'

export async function fetchHumanChallenge(): Promise<HumanChallenge> {
  const response = await http.get<ApiSuccess<HumanChallenge>>('/auth/human-challenge')
  return response.data.data
}

export async function fetchEmployeeSession(): Promise<EmployeeSession> {
  const response = await http.get<ApiSuccess<EmployeeSession>>('/employee/auth/session')
  return response.data.data
}

export async function loginEmployee(
  username: string,
  password: string,
  challengeId: string,
  sliderPosition: number,
): Promise<EmployeeSession> {
  const response = await http.post<ApiSuccess<EmployeeSession>>('/employee/auth/login', {
    username,
    password,
    challenge_id: challengeId,
    slider_position: sliderPosition,
  })
  return response.data.data
}

export async function logoutEmployee(): Promise<void> {
  await http.post('/employee/auth/logout')
}
