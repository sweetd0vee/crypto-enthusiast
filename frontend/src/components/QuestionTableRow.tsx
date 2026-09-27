import { Link } from 'react-router-dom'
import { formatDuration } from '../displayFormatting'
import type { Question } from '../types'
import { PencilIcon, QrIcon, TrashIcon } from './Icons'
import { StatusBadge } from './StatusBadge'
import { QuestionTiming } from './QuestionTiming'

interface QuestionTableRowProps {
  question: Question
  number: number | undefined
  onEdit: (question: Question) => void
  onShare: (question: Question) => void
  onDelete: (question: Question) => void
}

export function QuestionTableRow({
  question,
  number,
  onEdit,
  onShare,
  onDelete,
}: QuestionTableRowProps) {
  const canShare =
    question.effective_status === 'scheduled' ||
    question.effective_status === 'live'

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
            {question.options.length > 3 && (
              <span>+{question.options.length - 3}</span>
            )}
          </div>
        </div>
      </td>
      <td>
        <StatusBadge status={question.effective_status} />
      </td>
      <td className="time-cell">
        <QuestionTiming question={question} />
      </td>
      <td className="duration-cell">
        {formatDuration(question.duration_seconds)}
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
  )
}
