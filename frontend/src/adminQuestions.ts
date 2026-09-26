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

export function buildQuestionNumbers(
  questions: Question[],
): Map<number, number> {
  return new Map(
    [...questions]
      .sort((left, right) => left.id - right.id)
      .map((question, index) => [question.id, index + 1]),
  )
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
      const showDate = question.show_time
        ? new Date(question.show_time)
        : null
      const searchable = [
        question.name,
        ...question.options.map((option) => option.label),
      ]
        .join(' ')
        .toLocaleLowerCase()

      const matchesNumber =
        normalizedNumber === '' ||
        String(questionNumbers.get(question.id)).includes(normalizedNumber)
      const matchesStatus =
        filters.status === 'all' ||
        question.effective_status === filters.status
      const matchesSearch =
        normalizedSearch === '' || searchable.includes(normalizedSearch)
      const matchesTime =
        filters.time === 'all' ||
        (filters.time === 'without-date' && showDate === null) ||
        (filters.time === 'upcoming' &&
          showDate !== null &&
          showDate.getTime() > referenceTime.getTime()) ||
        (filters.time === 'today' &&
          showDate !== null &&
          showDate.toDateString() === referenceTime.toDateString())
      const matchesDuration =
        filters.duration === 'all' ||
        (filters.duration === 'short' &&
          question.duration_seconds <= 60) ||
        (filters.duration === 'medium' &&
          question.duration_seconds > 60 &&
          question.duration_seconds <= 300) ||
        (filters.duration === 'long' && question.duration_seconds > 300)

      return (
        matchesNumber &&
        matchesStatus &&
        matchesSearch &&
        matchesTime &&
        matchesDuration
      )
    })
    .sort((left, right) =>
      filters.sortDirection === 'asc'
        ? left.id - right.id
        : right.id - left.id,
    )
}
