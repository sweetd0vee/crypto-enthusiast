import { ApiError } from './api'
import type { ApiErrorCode, EffectiveStatus } from './types'

export const viewerMessages: Partial<Record<ApiErrorCode, string>> = {
  window_not_started: 'Голосование ещё не началось',
  window_closed: 'Время ролика вышло',
  already_voted: 'Вы уже ответили',
  not_published: 'Ссылка недействительна',
  not_found: 'Ссылка недействительна',
}

export const statusLabels: Record<EffectiveStatus, string> = {
  draft: 'Черновик',
  published: 'Опубликован',
  cancelled: 'Отменён',
  scheduled: 'Запланирован',
  live: 'В эфире',
  closed: 'Завершён',
}

export function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.body.message : fallback
}

export function toLocalInput(value: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}
