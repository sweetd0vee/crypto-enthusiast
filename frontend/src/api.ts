import type {
  ApiErrorBody,
  PublicQuestion,
  Question,
  QuestionInput,
  QuestionResult,
} from './types'

export class ApiError extends Error {
  status: number
  body: ApiErrorBody

  constructor(status: number, body: ApiErrorBody) {
    super(body.message)
    this.status = status
    this.body = body
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)

  if (!response.ok) {
    let body: ApiErrorBody
    try {
      body = (await response.json()) as ApiErrorBody
    } catch {
      body = { error: 'unavailable', message: 'Сервис временно недоступен' }
    }
    throw new ApiError(response.status, body)
  }

  if (response.status === 204) {
    return undefined as T
  }
  return response.json() as Promise<T>
}

function adminRequest<T>(url: string, init: RequestInit = {}): Promise<T> {
  const token = sessionStorage.getItem('adminToken')
  const headers = new Headers(init.headers)
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  return request<T>(url, { ...init, headers })
}

function jsonInit(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}

export const api = {
  getPublicQuestion: (id: string) =>
    request<PublicQuestion>(`/questionnaire/${id}`),

  vote: (id: string, option: string) =>
    request<{ status: 'accepted' }>(
      `/questionnaire/${id}/votes`,
      jsonInit('POST', { option }),
    ),

  listQuestions: () => adminRequest<Question[]>('/questions'),

  getQuestion: (id: string) =>
    adminRequest<Question>(`/questions/${id}`),

  createQuestion: (input: QuestionInput) =>
    adminRequest<Question>('/questions', jsonInit('POST', input)),

  updateQuestion: (id: number, input: QuestionInput) =>
    adminRequest<Question>(`/questions/${id}`, jsonInit('PUT', input)),

  deleteQuestion: (id: number) =>
    adminRequest<void>(`/questions/${id}`, { method: 'DELETE' }),

  getResults: (id: string) =>
    adminRequest<QuestionResult>(`/questions/${id}/results`),
}
