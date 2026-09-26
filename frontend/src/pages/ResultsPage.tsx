import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApiError, api } from '../api'
import { AdminLayout } from '../components/AdminLayout'
import type { QuestionResult } from '../types'
import { errorMessage, statusLabels } from '../ui'

export function ResultsPage() {
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
