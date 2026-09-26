import { type FormEvent, useCallback, useEffect, useState } from 'react'
import {
  BrowserRouter,
  Link,
  Navigate,
  Route,
  Routes,
  useNavigate,
  useParams,
} from 'react-router-dom'
import { ApiError, api } from './api'
import type {
  ApiErrorCode,
  EffectiveStatus,
  OptionInput,
  PublicQuestion,
  Question,
  QuestionInput,
  QuestionResult,
  QuestionStatus,
} from './types'
import './App.css'

const viewerMessages: Partial<Record<ApiErrorCode, string>> = {
  window_not_started: 'Голосование ещё не началось',
  window_closed: 'Время ролика вышло',
  already_voted: 'Вы уже ответили',
  not_published: 'Ссылка недействительна',
  not_found: 'Ссылка недействительна',
}

const statusLabels = {
  draft: 'Черновик',
  published: 'Опубликован',
  cancelled: 'Отменён',
  scheduled: 'Запланирован',
  live: 'В эфире',
  closed: 'Завершён',
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.body.message : fallback
}

function SearchIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <circle cx="11" cy="11" r="6.5" />
      <path d="m16 16 4 4" />
    </svg>
  )
}

function RefreshIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="M20 7v5h-5" />
      <path d="M19 12a7 7 0 1 0-2 5" />
    </svg>
  )
}

function PencilIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="m4 20 4.2-1 10.7-10.7a2.1 2.1 0 0 0-3-3L5.2 16Z" />
      <path d="m14.8 6.4 3 3" />
    </svg>
  )
}

function TrashIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7" />
      <path d="M10 11v5m4-5v5" />
    </svg>
  )
}

function StateCard({
  title,
  icon,
  busy = false,
}: {
  title: string
  icon?: string
  busy?: boolean
}) {
  return (
    <main className="viewer-shell">
      <section className="viewer-card state-card">
        {icon && <span className="success-icon">{icon}</span>}
        {busy && <span className="spinner" aria-hidden="true" />}
        <h1>{title}</h1>
      </section>
    </main>
  )
}

function ViewerPage() {
  const { id = '' } = useParams()
  const [question, setQuestion] = useState<PublicQuestion | null>(null)
  const [state, setState] = useState<
    'loading' | 'ready' | 'submitting' | 'success' | 'message' | 'network'
  >('loading')
  const [message, setMessage] = useState('')

  useEffect(() => {
    let active = true
    api
      .getPublicQuestion(id)
      .then((data) => {
        if (active) {
          setQuestion(data)
          setState('ready')
        }
      })
      .catch((error: unknown) => {
        if (!active) return
        if (error instanceof ApiError) {
          setMessage(
            viewerMessages[error.body.error] ?? 'Не удалось открыть голосование',
          )
          setState('message')
        } else {
          setMessage('Не удалось загрузить, проверьте подключение')
          setState('message')
        }
      })
    return () => {
      active = false
    }
  }, [id])

  async function submit(option: string) {
    if (state !== 'ready') return
    setState('submitting')
    try {
      await api.vote(id, option)
      setState('success')
    } catch (error) {
      if (error instanceof ApiError) {
        setMessage(
          viewerMessages[error.body.error] ??
            (error.body.error === 'invalid_option'
              ? 'Такого варианта больше нет'
              : error.body.message),
        )
        setState('message')
      } else {
        setMessage('Не удалось отправить, попробуйте ещё раз')
        setState('network')
      }
    }
  }

  if (state === 'loading') {
    return <StateCard title="Загружаем голосование…" busy />
  }
  if (state === 'success') {
    return <StateCard title="Ответ принят" icon="✓" />
  }
  if (state === 'message' || !question) {
    return <StateCard title={message} />
  }

  return (
    <main className="viewer-shell">
      <section className="viewer-card">
        <span className="eyebrow">ТВ-опрос</span>
        <h1>{question.name}</h1>
        <p className="deadline">
          Можно ответить до{' '}
          {new Date(question.closes_at).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </p>
        <div className="option-list">
          {question.options.map((option) => (
            <button
              className="option-button"
              disabled={state === 'submitting'}
              key={option.key}
              onClick={() => void submit(option.key)}
              type="button"
            >
              {option.label}
            </button>
          ))}
        </div>
        {state === 'network' && (
          <div className="inline-error">
            <span>{message}</span>
            <button type="button" onClick={() => setState('ready')}>
              Повторить
            </button>
          </div>
        )}
      </section>
    </main>
  )
}

function LoginPage() {
  const navigate = useNavigate()
  const [token, setToken] = useState('')

  function login(event: FormEvent) {
    event.preventDefault()
    if (!token.trim()) return
    sessionStorage.setItem('adminToken', token.trim())
    navigate('/admin', { replace: true })
  }

  return (
    <main className="login-shell">
      <form className="panel login-card" onSubmit={login}>
        <span className="eyebrow">Управление опросами</span>
        <h1>Вход в админку</h1>
        <label>
          Токен администратора
          <input
            autoFocus
            onChange={(event) => setToken(event.target.value)}
            placeholder="Введите токен"
            type="password"
            value={token}
          />
        </label>
        <button className="primary-button" type="submit">
          Войти
        </button>
      </form>
    </main>
  )
}

function AdminLayout({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate()
  return (
    <div className="admin-shell">
      <header className="admin-header">
        <Link className="brand" to="/admin">
          <span className="brand-mark">Q</span>
          TV Poll
        </Link>
        <button
          className="text-button"
          onClick={() => {
            sessionStorage.removeItem('adminToken')
            navigate('/admin/login')
          }}
          type="button"
        >
          Выйти
        </button>
      </header>
      {children}
    </div>
  )
}

function AdminPage() {
  const navigate = useNavigate()
  const [questions, setQuestions] = useState<Question[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState<Question | 'new' | null>(null)
  const [idFilter, setIdFilter] = useState('')
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | EffectiveStatus>(
    'all',
  )
  const [timeFilter, setTimeFilter] = useState<
    'all' | 'today' | 'upcoming' | 'without-date'
  >('all')
  const [durationFilter, setDurationFilter] = useState<
    'all' | 'short' | 'medium' | 'long'
  >('all')
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

  const normalizedSearch = search.trim().toLocaleLowerCase()
  const normalizedId = idFilter.replace(/\D/g, '')
  const filteredQuestions = questions
    .filter((question) => {
      const matchesStatus =
        statusFilter === 'all' || question.effective_status === statusFilter
      const matchesId =
        normalizedId === '' || String(question.id).includes(normalizedId)
      const searchable = [
        question.name,
        ...question.options.map((option) => option.label),
      ]
        .join(' ')
        .toLocaleLowerCase()
      const showDate = question.show_time
        ? new Date(question.show_time)
        : null
      const matchesTime =
        timeFilter === 'all' ||
        (timeFilter === 'without-date' && showDate === null) ||
        (timeFilter === 'upcoming' &&
          showDate !== null &&
          showDate.getTime() > filterReferenceTime.getTime()) ||
        (timeFilter === 'today' &&
          showDate !== null &&
          showDate.toDateString() === filterReferenceTime.toDateString())
      const matchesDuration =
        durationFilter === 'all' ||
        (durationFilter === 'short' &&
          question.duration_seconds <= 60) ||
        (durationFilter === 'medium' &&
          question.duration_seconds > 60 &&
          question.duration_seconds <= 300) ||
        (durationFilter === 'long' && question.duration_seconds > 300)
      return (
        matchesId &&
        matchesStatus &&
        matchesTime &&
        matchesDuration &&
        (normalizedSearch === '' || searchable.includes(normalizedSearch))
      )
    })
    .sort((left, right) => right.id - left.id)

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
            <p>Управляйте эфирами, вариантами ответов и результатами.</p>
          </div>
          <button
            className="primary-button"
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
          ) : filteredQuestions.length === 0 ? (
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
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr className="column-filters">
                    <th>
                      <input
                        aria-label="Фильтр по ID"
                        inputMode="numeric"
                        onChange={(event) => setIdFilter(event.target.value)}
                        placeholder="# ID"
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
                    <th>ID</th>
                    <th>Название</th>
                    <th>Статус</th>
                    <th>Время показа</th>
                    <th>Длительность</th>
                    <th>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredQuestions.map((question) => (
                    <tr key={question.id}>
                      <td>
                        <span className="id-badge">#{question.id}</span>
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
                  ))}
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

function toLocalInput(value: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}

function QuestionEditor({
  question,
  onClose,
  onSaved,
}: {
  question?: Question
  onClose: () => void
  onSaved: () => Promise<void>
}) {
  const [name, setName] = useState(question?.name ?? '')
  const [showTime, setShowTime] = useState(
    toLocalInput(question?.show_time ?? null),
  )
  const [duration, setDuration] = useState(question?.duration_seconds ?? 60)
  const [status, setStatus] = useState<QuestionStatus>(
    question?.status ?? 'draft',
  )
  const [options, setOptions] = useState<OptionInput[]>(
    question?.options.map(({ key, label }) => ({ key, label })) ?? [
      { key: 'yes', label: 'Да' },
      { key: 'no', label: 'Нет' },
    ],
  )
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  function updateOption(index: number, field: keyof OptionInput, value: string) {
    setOptions((current) =>
      current.map((option, optionIndex) =>
        optionIndex === index ? { ...option, [field]: value } : option,
      ),
    )
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    setError('')
    if (status === 'published' && !showTime) {
      setError('Для публикации укажите время показа')
      return
    }
    const input: QuestionInput = {
      name,
      status,
      show_time: showTime ? new Date(showTime).toISOString() : null,
      duration_seconds: duration,
      options,
    }
    setSaving(true)
    try {
      if (question) {
        await api.updateQuestion(question.id, input)
      } else {
        await api.createQuestion(input)
      }
      await onSaved()
    } catch (requestError) {
      const code =
        requestError instanceof ApiError ? requestError.body.error : null
      setError(
        code === 'options_locked'
          ? 'Нельзя менять варианты после появления голосов'
          : errorMessage(requestError, 'Не удалось сохранить вопрос'),
      )
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section
        aria-labelledby="editor-title"
        aria-modal="true"
        className="modal"
        role="dialog"
      >
        <div className="modal-heading">
          <div>
            <span className="eyebrow">
              {question ? `Вопрос #${question.id}` : 'Новый вопрос'}
            </span>
            <h2 id="editor-title">
              {question ? 'Изменить вопрос' : 'Создать вопрос'}
            </h2>
          </div>
          <button
            aria-label="Закрыть"
            className="close-button"
            onClick={onClose}
            type="button"
          >
            ×
          </button>
        </div>
        <form className="editor-form" onSubmit={(event) => void save(event)}>
          <label>
            Название
            <input
              onChange={(event) => setName(event.target.value)}
              required
              value={name}
            />
          </label>
          <div className="form-grid">
            <label>
              Время показа
              <input
                onChange={(event) => setShowTime(event.target.value)}
                type="datetime-local"
                value={showTime}
              />
            </label>
            <label>
              Длительность, сек.
              <input
                max={3600}
                min={10}
                onChange={(event) => setDuration(Number(event.target.value))}
                required
                type="number"
                value={duration}
              />
            </label>
            <label>
              Статус
              <select
                onChange={(event) =>
                  setStatus(event.target.value as QuestionStatus)
                }
                value={status}
              >
                <option value="draft">Черновик</option>
                <option value="published">Опубликован</option>
                {question && <option value="cancelled">Отменён</option>}
              </select>
            </label>
          </div>
          <fieldset>
            <legend>Варианты ответа</legend>
            <div className="option-editor">
              {options.map((option, index) => (
                <div className="option-row" key={index}>
                  <input
                    aria-label={`Ключ варианта ${index + 1}`}
                    maxLength={64}
                    onChange={(event) =>
                      updateOption(index, 'key', event.target.value)
                    }
                    placeholder="Ключ"
                    required
                    value={option.key}
                  />
                  <input
                    aria-label={`Подпись варианта ${index + 1}`}
                    onChange={(event) =>
                      updateOption(index, 'label', event.target.value)
                    }
                    placeholder="Подпись"
                    required
                    value={option.label}
                  />
                  <button
                    aria-label="Удалить вариант"
                    disabled={options.length <= 2}
                    onClick={() =>
                      setOptions((current) =>
                        current.filter((_, optionIndex) => optionIndex !== index),
                      )
                    }
                    type="button"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
            <button
              className="text-button"
              disabled={options.length >= 10}
              onClick={() =>
                setOptions((current) => [
                  ...current,
                  { key: `option${current.length + 1}`, label: '' },
                ])
              }
              type="button"
            >
              + Добавить вариант
            </button>
          </fieldset>
          {error && <div className="alert">{error}</div>}
          <div className="form-actions">
            <button className="secondary-button" onClick={onClose} type="button">
              Отмена
            </button>
            <button className="primary-button" disabled={saving} type="submit">
              {saving ? 'Сохраняем…' : 'Сохранить'}
            </button>
          </div>
        </form>
      </section>
    </div>
  )
}

function ResultsPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const [result, setResult] = useState<QuestionResult | null>(null)
  const [error, setError] = useState('')

  const loadResults = useCallback(async () => {
    try {
      setResult(await api.getResults(id))
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
      setError(errorMessage(requestError, 'Не удалось загрузить результаты'))
    }
  }, [id, navigate])

  useEffect(() => {
    // Loading remote state is the intended synchronization for this page.
    // oxlint-disable-next-line react/set-state-in-effect
    void loadResults()
  }, [loadResults])

  useEffect(() => {
    if (result?.effective_status !== 'live') return
    const timer = window.setInterval(() => void loadResults(), 2000)
    return () => window.clearInterval(timer)
  }, [loadResults, result?.effective_status])

  return (
    <AdminLayout>
      <main className="admin-main results-main">
        <Link className="back-link" to="/admin">
          ← Все вопросы
        </Link>
        {error && <div className="alert">{error}</div>}
        {!result ? (
          <section className="panel empty-state">Загружаем результаты…</section>
        ) : (
          <>
            <div className="page-heading result-heading">
              <div>
                <span className="eyebrow">Результаты · #{result.question_id}</span>
                <h1>{result.name}</h1>
              </div>
              <div className="result-total">
                <strong>{result.total.toLocaleString()}</strong>
                <span>ответов</span>
              </div>
            </div>
            <div className="result-meta">
              <span className={`status status-${result.effective_status}`}>
                {statusLabels[result.effective_status]}
              </span>
              {result.effective_status === 'live' && (
                <span className="live-note">Обновляется каждые 2 секунды</span>
              )}
            </div>
            <section className="panel results-panel">
              {result.total === 0 && (
                <p className="empty-results">Пока нет ответов</p>
              )}
              <div className="bars">
                {result.counts.map((row) => {
                  const percent =
                    result.total === 0 ? 0 : (row.count / result.total) * 100
                  return (
                    <div className="bar-row" key={row.key}>
                      <div className="bar-label">
                        <span>{row.label}</span>
                        <strong>
                          {row.count.toLocaleString()} · {percent.toFixed(1)}%
                        </strong>
                      </div>
                      <div className="bar-track">
                        <div
                          className="bar-fill"
                          style={{ width: `${percent}%` }}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>
            </section>
          </>
        )}
      </main>
    </AdminLayout>
  )
}

function RequireAuth({ children }: { children: React.ReactNode }) {
  return sessionStorage.getItem('adminToken') ? (
    children
  ) : (
    <Navigate replace to="/admin/login" />
  )
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/q/:id" element={<ViewerPage />} />
        <Route path="/admin/login" element={<LoginPage />} />
        <Route
          path="/admin"
          element={
            <RequireAuth>
              <AdminPage />
            </RequireAuth>
          }
        />
        <Route
          path="/admin/questions/:id"
          element={
            <RequireAuth>
              <ResultsPage />
            </RequireAuth>
          }
        />
        <Route path="*" element={<Navigate replace to="/admin" />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
