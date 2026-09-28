import type { EffectiveStatus } from './types'

export const statusLabels: Record<EffectiveStatus, string> = {
  draft: 'Черновик',
  cancelled: 'Отменён',
  scheduled: 'Запланирован',
  live: 'В эфире',
  closed: 'Завершён',
}

/** Длительность окна для таблицы: минуты, если ≥ 60 секунд. */
export function formatDuration(seconds: number): string {
  if (seconds >= 60) return `${Math.floor(seconds / 60)} мин.`
  return `${seconds} сек.`
}

/** ISO с сервера → значение для `<input type="datetime-local">` в локальной зоне. */
export function toLocalDateTimeInput(value: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}
