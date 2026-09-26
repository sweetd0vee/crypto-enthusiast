import { useEffect, useState } from 'react'
import type { Question } from '../types'

function formatRemaining(milliseconds: number): string {
  const totalSeconds = Math.max(0, Math.ceil(milliseconds / 1000))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60

  if (hours > 0) {
    return `${hours} ч ${String(minutes).padStart(2, '0')} мин`
  }
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

export function QuestionTiming({ question }: { question: Question }) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (
      question.effective_status !== 'live' &&
      question.effective_status !== 'scheduled'
    ) {
      return
    }

    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [question.effective_status])

  if (!question.show_time) return <span>—</span>

  const startsAt = new Date(question.show_time).getTime()
  const closesAt = startsAt + question.duration_seconds * 1000
  const isLive = question.effective_status === 'live' && closesAt > now
  const isScheduled =
    question.effective_status === 'scheduled' && startsAt > now

  return (
    <div className="time-stack">
      <span>{new Date(question.show_time).toLocaleString()}</span>
      {isLive && (
        <small className="timing-hint timing-live">
          Завершение через {formatRemaining(closesAt - now)}
        </small>
      )}
      {isScheduled && (
        <small className="timing-hint">
          Старт через {formatRemaining(startsAt - now)}
        </small>
      )}
    </div>
  )
}
