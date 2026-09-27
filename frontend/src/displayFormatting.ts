import type { EffectiveStatus } from './types'

export const statusLabels: Record<EffectiveStatus, string> = {
  draft: 'Черновик',
  cancelled: 'Отменён',
  scheduled: 'Запланирован',
  live: 'В эфире',
  closed: 'Завершён',
}

export function formatDuration(seconds: number): string {
  if (seconds >= 60) return `${Math.floor(seconds / 60)} мин.`
  return `${seconds} сек.`
}

export function toLocalDateTimeInput(value: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}
