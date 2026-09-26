import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  buildQuestionNumbers,
  filterQuestions,
  type DurationFilter,
  type SortDirection,
  type TimeFilter,
} from '../adminQuestions'
import { ApiError, api } from '../api'
import { AdminLayout } from '../components/AdminLayout'
import {
  PencilIcon,
  RefreshIcon,
  SearchIcon,
  TrashIcon,
} from '../components/Icons'
import { QuestionEditor } from '../components/QuestionEditor'
import type { EffectiveStatus, Question } from '../types'
import { errorMessage, statusLabels } from '../ui'

export function AdminPage() {
  const navigate = useNavigate()
  const [questions, setQuestions] = useState<Question[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState<Question | 'new' | null>(null)
  const [idFilter, setIdFilter] = useState('')
  const [idSortDirection, setIdSortDirection] =
    useState<SortDirection>('asc')
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | EffectiveStatus>(
    'all',
  )
  const [timeFilter, setTimeFilter] = useState<TimeFilter>('all')
  const [durationFilter, setDurationFilter] =
    useState<DurationFilter>('all')
  const [filterReferenceTime] = useState(() => new Date())

  const loadQuestions = useCallback(async () => {
    try {
      setQuestions(await api.listQuestions())
      setError('')
    } catch (requestError) {
      if (
        requestError instanceof ApiError &&
        requestError.body.error === 'unauthorized'
      ) {
        sessionStorage.removeItem('adminToken')
        navigate('/admin/login', { replace: true })
        return
      }
      setError(errorMessage(requestError, 'Не удалось загрузить вопросы'))
    } finally {
      setLoading(false)
    }
  }, [navigate])

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
      const code =
        requestError instanceof ApiError ? requestError.body.error : null
      setError(
        code === 'delete_forbidden'
          ? 'Нельзя удалить опубликованный вопрос или вопрос с голосами'
          : errorMessage(requestError, 'Не удалось удалить вопрос'),
      )
    }
  }

  const questionNumbers = buildQuestionNumbers(questions)
  const filteredQuestions = filterQuestions(
    questions,
    {
      number: idFilter,
      search,
      status: statusFilter,
      time: timeFilter,
      duration: durationFilter,
      sortDirection: idSortDirection,
    },
    filterReferenceTime,
    questionNumbers,
  )

  const liveCount = questions.filter(
    (question) => question.effective_status === 'live',
  ).length
  const scheduledCount = questions.filter(
    (question) => question.effective_status === 'scheduled',
  ).length
  const draftCount = questions.filter(
    (question) => question.effective_status === 'draft',
  ).length
  const filtersActive =
    idFilter !== '' ||
    search !== '' ||
    statusFilter !== 'all' ||
    timeFilter !== 'all' ||
    durationFilter !== 'all'

  function resetFilters() {
    setIdFilter('')
    setSearch('')
    setStatusFilter('all')
    setTimeFilter('all')
    setDurationFilter('all')
  }

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
        <section className="stats-grid" aria-label="Сводка по вопросам">
          <div className="stat-card">
            <span>Всего вопросов</span>
            <strong>{questions.length}</strong>
          </div>
          <div className="stat-card stat-card-live">
            <span>Сейчас в эфире</span>
            <strong>{liveCount}</strong>
          </div>
          <div className="stat-card">
            <span>Запланировано</span>
            <strong>{scheduledCount}</strong>
          </div>
          <div className="stat-card">
            <span>Черновики</span>
            <strong>{draftCount}</strong>
          </div>
        </section>
        <section className="panel table-panel">
          {!loading && questions.length > 0 && (
            <div className="table-summary">
              <span>
                Показано {filteredQuestions.length} из {questions.length}
              </span>
              <button
                className="refresh-button"
                disabled={loading}
                onClick={() => void loadQuestions()}
                type="button"
              >
                <RefreshIcon /> Обновить
              </button>
            </div>
          )}
          {loading ? (
            <p className="empty-state">Загружаем вопросы…</p>
          ) : questions.length === 0 ? (
            <p className="empty-state">Вопросов пока нет. Создайте первый.</p>
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr className="column-filters">
                    <th>
                      <input
                        aria-label="Фильтр по номеру"
                        inputMode="numeric"
                        onChange={(event) => setIdFilter(event.target.value)}
                        placeholder="№"
                        value={idFilter}
                      />
                    </th>
                    <th>
                      <div className="column-search">
                        <SearchIcon />
                        <input
                          aria-label="Поиск по названию и вариантам"
                          onChange={(event) => setSearch(event.target.value)}
                          placeholder="Название или вариант ответа"
                          type="search"
                          value={search}
                        />
                      </div>
                    </th>
                    <th>
                      <select
                        aria-label="Фильтр по статусу"
                        onChange={(event) =>
                          setStatusFilter(
                            event.target.value as 'all' | EffectiveStatus,
                          )
                        }
                        value={statusFilter}
                      >
                        <option value="all">Все статусы</option>
                        <option value="live">В эфире</option>
                        <option value="scheduled">Запланированные</option>
                        <option value="draft">Черновики</option>
                        <option value="closed">Завершённые</option>
                        <option value="cancelled">Отменённые</option>
                      </select>
                    </th>
                    <th>
                      <select
                        aria-label="Фильтр по времени показа"
                        onChange={(event) =>
                          setTimeFilter(
                            event.target.value as typeof timeFilter,
                          )
                        }
                        value={timeFilter}
                      >
                        <option value="all">Любое время</option>
                        <option value="today">Сегодня</option>
                        <option value="upcoming">Предстоящие</option>
                        <option value="without-date">Без даты</option>
                      </select>
                    </th>
                    <th>
                      <select
                        aria-label="Фильтр по длительности"
                        onChange={(event) =>
                          setDurationFilter(
                            event.target.value as typeof durationFilter,
                          )
                        }
                        value={durationFilter}
                      >
                        <option value="all">Любая</option>
                        <option value="short">До 1 минуты</option>
                        <option value="medium">1–5 минут</option>
                        <option value="long">Больше 5 минут</option>
                      </select>
                    </th>
                    <th>
                      <button
                        className="reset-filters"
                        disabled={!filtersActive}
                        onClick={resetFilters}
                        type="button"
                      >
                        Сбросить
                      </button>
                    </th>
                  </tr>
                  <tr>
                    <th>
                      <button
                        aria-label={`Сортировать номера ${
                          idSortDirection === 'asc'
                            ? 'по убыванию'
                            : 'по возрастанию'
                        }`}
                        className="sort-button"
                        onClick={() =>
                          setIdSortDirection((current) =>
                            current === 'asc' ? 'desc' : 'asc',
                          )
                        }
                        type="button"
                      >
                        № <span>{idSortDirection === 'asc' ? '↑' : '↓'}</span>
                      </button>
                    </th>
                    <th>Название</th>
                    <th>Статус</th>
                    <th>Время показа</th>
                    <th>Длительность</th>
                    <th>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredQuestions.length === 0 ? (
                    <tr className="no-results-row">
                      <td colSpan={6}>
                        <div className="empty-state">
                          <strong>Ничего не найдено</strong>
                          <span>Измените запрос или сбросьте фильтры.</span>
                          <button
                            className="text-button"
                            onClick={resetFilters}
                            type="button"
                          >
                            Сбросить фильтры
                          </button>
                        </div>
                      </td>
                    </tr>
                  ) : (
                    filteredQuestions.map((question) => (
                      <tr key={question.id}>
                        <td>
                          <span className="id-badge">
                            #{questionNumbers.get(question.id)}
                          </span>
                        </td>
                        <td>
                          <div className="question-cell">
                            <strong>{question.name}</strong>
                            <div className="option-preview">
                              {question.options.slice(0, 3).map((option) => (
                                <span key={option.key}>{option.label}</span>
                              ))}
                              {question.options.length > 3 && (
                                <span>+{question.options.length - 3}</span>
                              )}
                            </div>
                          </div>
                        </td>
                        <td>
                          <span
                            className={`status status-${question.effective_status}`}
                          >
                            {statusLabels[question.effective_status]}
                          </span>
                        </td>
                        <td className="time-cell">
                          {question.show_time
                            ? new Date(question.show_time).toLocaleString()
                            : '—'}
                        </td>
                        <td className="duration-cell">
                          {question.duration_seconds >= 60
                            ? `${Math.floor(question.duration_seconds / 60)} мин.`
                            : `${question.duration_seconds} сек.`}
                        </td>
                        <td>
                          <div className="row-actions">
                            {question.effective_status === 'draft' ? (
                              <span
                                className="action-button action-disabled"
                                title="У черновика ещё нет результатов"
                              >
                                Результаты
                              </span>
                            ) : (
                              <Link
                                className="action-button action-results"
                                to={`/admin/questions/${question.id}`}
                              >
                                Результаты
                              </Link>
                            )}
                            <button
                              aria-label={`Изменить вопрос «${question.name}»`}
                              className="icon-action"
                              onClick={() => setEditing(question)}
                              title="Изменить"
                              type="button"
                            >
                              <PencilIcon />
                            </button>
                            <button
                              aria-label={`Удалить вопрос «${question.name}»`}
                              className="icon-action danger-link"
                              disabled={question.status !== 'draft'}
                              onClick={() => void remove(question)}
                              title={
                                question.status === 'draft'
                                  ? 'Удалить черновик'
                                  : 'Удалить можно только черновик'
                              }
                              type="button"
                            >
                              <TrashIcon />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </section>
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
    </AdminLayout>
  )
}
