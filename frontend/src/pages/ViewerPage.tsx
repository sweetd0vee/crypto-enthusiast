import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ApiError, api } from '../api'
import type { PublicQuestion } from '../types'
import { viewerMessages } from '../ui'

type ViewerState =
  | 'loading'
  | 'ready'
  | 'submitting'
  | 'success'
  | 'message'
  | 'network'

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

export function ViewerPage() {
  const { id = '' } = useParams()
  const [question, setQuestion] = useState<PublicQuestion | null>(null)
  const [state, setState] = useState<ViewerState>('loading')
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
        } else {
          setMessage('Не удалось загрузить, проверьте подключение')
        }
        setState('message')
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
