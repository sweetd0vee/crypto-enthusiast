import { Link } from 'react-router-dom'
import type { QuestionFilters } from '../adminQuestions'
import { PencilIcon, QrIcon, SearchIcon, TrashIcon } from './Icons'
import { QuestionTiming } from './QuestionTiming'
import type { Question } from '../types'
import { formatDuration, statusLabels } from '../ui'

interface QuestionTableProps {
  questions: Question[]
  filteredQuestions: Question[]
  questionNumbers: Map<number, number>
  loading: boolean
  filters: QuestionFilters
  filtersActive: boolean
  onChange: (patch: Partial<QuestionFilters>) => void
  onReset: () => void
  onEdit: (question: Question) => void
  onShare: (question: Question) => void
  onDelete: (question: Question) => void
}

export function QuestionTable({
  questions,
  filteredQuestions,
  questionNumbers,
  loading,
  filters,
  filtersActive,
  onChange,
  onReset,
  onEdit,
  onShare,
  onDelete,
}: QuestionTableProps) {
  return (
    <section className="panel table-panel">
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
                    onChange={(event) => onChange({ number: event.target.value })}
                    placeholder="№"
                    value={filters.number}
                  />
                </th>
                <th>
                  <div className="column-search">
                    <SearchIcon />
                    <input
                      aria-label="Поиск по названию и вариантам"
                      onChange={(event) => onChange({ search: event.target.value })}
                      placeholder="Название или вариант ответа"
                      type="search"
                      value={filters.search}
                    />
                  </div>
                </th>
                <th>
                  <select
                    aria-label="Фильтр по статусу"
                    onChange={(event) =>
                      onChange({
                        status: event.target.value as QuestionFilters['status'],
                      })
                    }
                    value={filters.status}
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
                      onChange({ time: event.target.value as QuestionFilters['time'] })
                    }
                    value={filters.time}
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
                      onChange({
                        duration: event.target.value as QuestionFilters['duration'],
                      })
                    }
                    value={filters.duration}
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
                    onClick={onReset}
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
                      filters.sortDirection === 'asc' ? 'по убыванию' : 'по возрастанию'
                    }`}
                    className="sort-button"
                    onClick={() =>
                      onChange({
                        sortDirection: filters.sortDirection === 'asc' ? 'desc' : 'asc',
                      })
                    }
                    type="button"
                  >
                    № <span>{filters.sortDirection === 'asc' ? '↑' : '↓'}</span>
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
                      <button className="text-button" onClick={onReset} type="button">
                        Сбросить фильтры
                      </button>
                    </div>
                  </td>
                </tr>
              ) : (
                filteredQuestions.map((question) => (
                  <QuestionRow
                    key={question.id}
                    number={questionNumbers.get(question.id)}
                    onDelete={onDelete}
                    onEdit={onEdit}
                    onShare={onShare}
                    question={question}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function QuestionRow({
  question,
  number,
  onEdit,
  onShare,
  onDelete,
}: {
  question: Question
  number: number | undefined
  onEdit: (question: Question) => void
  onShare: (question: Question) => void
  onDelete: (question: Question) => void
}) {
  const canShare =
    question.effective_status === 'scheduled' || question.effective_status === 'live'

  return (
    <tr>
      <td>
        <span className="id-badge">#{number}</span>
      </td>
      <td>
        <div className="question-cell">
          <strong>{question.name}</strong>
          <div className="option-preview">
            {question.options.slice(0, 3).map((option) => (
              <span key={option.key}>{option.label}</span>
            ))}
            {question.options.length > 3 && <span>+{question.options.length - 3}</span>}
          </div>
        </div>
      </td>
      <td>
        <span className={`status status-${question.effective_status}`}>
          {statusLabels[question.effective_status]}
        </span>
      </td>
      <td className="time-cell">
        <QuestionTiming question={question} />
      </td>
      <td className="duration-cell">{formatDuration(question.duration_seconds)}</td>
      <td>
        <div className="row-actions">
          {question.effective_status === 'draft' ? (
            <span className="action-button action-disabled" title="У черновика ещё нет результатов">
              Результаты
            </span>
          ) : (
            <Link className="action-button action-results" to={`/admin/questions/${question.id}`}>
              Результаты
            </Link>
          )}
          {canShare && (
            <button
              aria-label={`Показать QR-код для «${question.name}»`}
              className="icon-action qr-action"
              onClick={() => onShare(question)}
              title="QR-код и ссылка"
              type="button"
            >
              <QrIcon />
            </button>
          )}
          <button
            aria-label={`Изменить вопрос «${question.name}»`}
            className="icon-action"
            onClick={() => onEdit(question)}
            title="Изменить"
            type="button"
          >
            <PencilIcon />
          </button>
          <button
            aria-label={`Удалить вопрос «${question.name}»`}
            className="icon-action danger-link"
            disabled={question.status !== 'draft'}
            onClick={() => onDelete(question)}
            title={
              question.status === 'draft' ? 'Удалить черновик' : 'Удалить можно только черновик'
            }
            type="button"
          >
            <TrashIcon />
          </button>
        </div>
      </td>
    </tr>
  )
}
