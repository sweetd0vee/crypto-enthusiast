import { ApiError } from './api'
import type { ApiErrorCode } from './types'

export const viewerMessages: Partial<Record<ApiErrorCode, string>> = {
  window_not_started: 'Голосование ещё не началось',
  window_closed: 'Время ролика вышло',
  already_voted: 'Вы уже ответили',
  not_published: 'Ссылка недействительна',
  not_found: 'Ссылка недействительна',
}

const adminMessages: Partial<Record<ApiErrorCode, string>> = {
  delete_forbidden: 'Нельзя удалить опубликованный вопрос или вопрос с голосами',
  options_locked: 'Нельзя менять варианты после появления голосов',
}

export function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.body.message : fallback
}

export function adminErrorMessage(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError)) return fallback
  return adminMessages[error.body.error] ?? error.body.message
}
