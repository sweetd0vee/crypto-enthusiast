import type { EffectiveStatus, Question } from '../types'

const CARDS: Array<{
  status: EffectiveStatus | 'total'
  label: string
  className: string
}> = [
  { status: 'total', label: 'Всего вопросов', className: 'stat-card-total' },
  { status: 'live', label: 'Сейчас в эфире', className: 'stat-card-live' },
  { status: 'scheduled', label: 'Запланировано', className: 'stat-card-scheduled' },
  { status: 'closed', label: 'Завершено', className: 'stat-card-closed' },
  { status: 'draft', label: 'Черновики', className: 'stat-card-draft' },
]

function count(questions: Question[], status: EffectiveStatus | 'total'): number {
  if (status === 'total') return questions.length
  return questions.filter((question) => question.effective_status === status).length
}

export function QuestionStats({ questions }: { questions: Question[] }) {
  return (
    <section className="stats-grid" aria-label="Сводка по вопросам">
      {CARDS.map((card) => (
        <div className={`stat-card ${card.className}`} key={card.status}>
          <span>{card.label}</span>
          <strong>{count(questions, card.status)}</strong>
        </div>
      ))}
    </section>
  )
}
