import { ApiError } from './api'
import type { ApiErrorCode } from './types'

export const viewerMessages: Partial<Record<ApiErrorCode, string>> = {
  window_not_started: 'Голосование ещё не началось',
  window_closed: 'Время ролика вышло',
  already_voted: 'Вы уже ответили',
  not_published: 'Ссылка недействительна',
  not_found: 'Ссылка недействительна',
}

export function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.body.message : fallback
}
