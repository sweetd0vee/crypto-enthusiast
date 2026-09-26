import { type FormEvent, useState } from 'react'
import { ApiError, api } from '../api'
import type {
  OptionInput,
  Question,
  QuestionInput,
  QuestionStatus,
} from '../types'
import { errorMessage, toLocalInput } from '../ui'

export function QuestionEditor({
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
