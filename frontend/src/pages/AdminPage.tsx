import { useCallback, useEffect, useState } from 'react'
import {
  buildQuestionNumbers,
  emptyFilters,
  filterQuestions,
  filtersAreActive,
  type QuestionFilters,
} from '../adminQuestions'
import { ApiError, api } from '../api'
import { AdminLayout } from '../components/AdminLayout'
import { QuestionEditor } from '../components/QuestionEditor'
import { QuestionShareDialog } from '../components/QuestionShareDialog'
import { QuestionStats } from '../components/QuestionStats'
import { QuestionTable } from '../components/QuestionTable'
import type { Question } from '../types'
import { errorMessage } from '../ui'
import { useAdminGuard } from '../useAdminGuard'

export function AdminPage() {
  const rejectUnauthorized = useAdminGuard()
  const [questions, setQuestions] = useState<Question[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState<Question | 'new' | null>(null)
  const [sharing, setSharing] = useState<Question | null>(null)
  const [filters, setFilters] = useState<QuestionFilters>(emptyFilters)
  const [filterReferenceTime] = useState(() => new Date())

  const loadQuestions = useCallback(async () => {
    try {
      setQuestions(await api.listQuestions())
      setError('')
    } catch (requestError) {
      if (rejectUnauthorized(requestError)) return
      setError(errorMessage(requestError, 'Не удалось загрузить вопросы'))
    } finally {
      setLoading(false)
    }
  }, [rejectUnauthorized])

  useEffect(() => {
    // Loading remote state is the intended synchronization for this page.
    // oxlint-disable-next-line react/set-state-in-effect
    void loadQuestions()
  }, [loadQuestions])

  async function remove(question: Question) {
    if (!window.confirm(`Удалить «${question.name}»?`)) return
    try {
      await api.deleteQuestion(question.id)
      await loadQuestions()
    } catch (requestError) {
      if (rejectUnauthorized(requestError)) return
      const code = requestError instanceof ApiError ? requestError.body.error : null
      setError(
        code === 'delete_forbidden'
          ? 'Нельзя удалить опубликованный вопрос или вопрос с голосами'
          : errorMessage(requestError, 'Не удалось удалить вопрос'),
      )
    }
  }

  function changeFilters(patch: Partial<QuestionFilters>) {
    setFilters((current) => ({ ...current, ...patch }))
  }

  function resetFilters() {
    setFilters((current) => ({ ...emptyFilters, sortDirection: current.sortDirection }))
  }

  const questionNumbers = buildQuestionNumbers(questions)

  return (
    <AdminLayout>
      <main className="admin-main">
        <div className="page-heading">
          <div>
            <span className="eyebrow">Админка</span>
            <h1>Вопросы</h1>
          </div>
          <button
            className="primary-button create-button"
            onClick={() => setEditing('new')}
            type="button"
          >
            + Создать
          </button>
        </div>
        {error && <div className="alert">{error}</div>}
        <QuestionStats questions={questions} />
        <QuestionTable
          filteredQuestions={filterQuestions(
            questions,
            filters,
            filterReferenceTime,
            questionNumbers,
          )}
          filters={filters}
          filtersActive={filtersAreActive(filters)}
          loading={loading}
          onChange={changeFilters}
          onDelete={(question) => void remove(question)}
          onEdit={setEditing}
          onReset={resetFilters}
          onShare={setSharing}
          questionNumbers={questionNumbers}
          questions={questions}
        />
      </main>
      {editing && (
        <QuestionEditor
          question={editing === 'new' ? undefined : editing}
          onClose={() => setEditing(null)}
          onSaved={async () => {
            setEditing(null)
            await loadQuestions()
          }}
        />
      )}
      {sharing && (
        <QuestionShareDialog question={sharing} onClose={() => setSharing(null)} />
      )}
    </AdminLayout>
  )
}
