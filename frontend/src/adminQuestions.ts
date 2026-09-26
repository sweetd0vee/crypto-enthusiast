import type { EffectiveStatus, Question } from './types'

export type TimeFilter = 'all' | 'today' | 'upcoming' | 'without-date'
export type DurationFilter = 'all' | 'short' | 'medium' | 'long'
export type SortDirection = 'asc' | 'desc'

export interface QuestionFilters {
  number: string
  search: string
  status: 'all' | EffectiveStatus
  time: TimeFilter
  duration: DurationFilter
  sortDirection: SortDirection
}

export const emptyFilters: QuestionFilters = {
  number: '',
  search: '',
  status: 'all',
  time: 'all',
  duration: 'all',
  sortDirection: 'asc',
}

export function filtersAreActive(filters: QuestionFilters): boolean {
  return (
    filters.number !== '' ||
    filters.search !== '' ||
    filters.status !== 'all' ||
    filters.time !== 'all' ||
    filters.duration !== 'all'
  )
}

export function buildQuestionNumbers(
  questions: Question[],
): Map<number, number> {
  return new Map(
    [...questions]
      .sort((left, right) => left.id - right.id)
      .map((question, index) => [question.id, index + 1]),
  )
}

function matchesTime(
  showDate: Date | null,
  time: TimeFilter,
  referenceTime: Date,
): boolean {
  switch (time) {
    case 'all':
      return true
    case 'without-date':
      return showDate === null
    case 'upcoming':
      return showDate !== null && showDate.getTime() > referenceTime.getTime()
    case 'today':
      return (
        showDate !== null &&
        showDate.toDateString() === referenceTime.toDateString()
      )
  }
}

function matchesDuration(seconds: number, duration: DurationFilter): boolean {
  switch (duration) {
    case 'all':
      return true
    case 'short':
      return seconds <= 60
    case 'medium':
      return seconds > 60 && seconds <= 300
    case 'long':
      return seconds > 300
  }
}

export function filterQuestions(
  questions: Question[],
  filters: QuestionFilters,
  referenceTime: Date,
  questionNumbers: Map<number, number>,
): Question[] {
  const normalizedSearch = filters.search.trim().toLocaleLowerCase()
  const normalizedNumber = filters.number.replace(/\D/g, '')

  return questions
    .filter((question) => {
      const showDate = question.show_time ? new Date(question.show_time) : null
      const searchable = [question.name, ...question.options.map((option) => option.label)]
        .join(' ')
        .toLocaleLowerCase()
      const shownNumber = String(questionNumbers.get(question.id))

      return (
        (normalizedNumber === '' || shownNumber.includes(normalizedNumber)) &&
        (filters.status === 'all' || question.effective_status === filters.status) &&
        (normalizedSearch === '' || searchable.includes(normalizedSearch)) &&
        matchesTime(showDate, filters.time, referenceTime) &&
        matchesDuration(question.duration_seconds, filters.duration)
      )
    })
    .sort((left, right) =>
      filters.sortDirection === 'asc' ? left.id - right.id : right.id - left.id,
    )
}
