import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { AdminLayout } from '../components/AdminLayout'
import { StatusBadge } from '../components/StatusBadge'
import { errorMessage } from '../errorMessages'
import type { QuestionResult } from '../types'
import { useAdminGuard } from '../useAdminGuard'

const RESULTS_POLL_INTERVAL_MS = 2_000

export function ResultsPage() {
  const { id = '' } = useParams()
  const rejectUnauthorized = useAdminGuard()
  const [result, setResult] = useState<QuestionResult | null>(null)
  const [error, setError] = useState('')

  const loadResults = useCallback(async () => {
    try {
      setResult(await api.getResults(id))
      setError('')
    } catch (requestError) {
      if (rejectUnauthorized(requestError)) return
      setError(errorMessage(requestError, 'Не удалось загрузить результаты'))
    }
  }, [id, rejectUnauthorized])

  useEffect(() => {
    // Loading remote state is the intended synchronization for this page.
    // oxlint-disable-next-line react/set-state-in-effect
    void loadResults()
  }, [loadResults])

  useEffect(() => {
    if (result?.effective_status !== 'live') return
    const timer = window.setInterval(
      () => void loadResults(),
      RESULTS_POLL_INTERVAL_MS,
    )
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
              <StatusBadge status={result.effective_status} />
              {result.effective_status === 'live' && (
                <span className="live-note">
                  Обновляется каждые {RESULTS_POLL_INTERVAL_MS / 1000} секунды
                </span>
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
