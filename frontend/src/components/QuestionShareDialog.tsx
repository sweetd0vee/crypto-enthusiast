import { useRef, useState } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import type { Question } from '../types'
import { statusLabels } from '../ui'

export function QuestionShareDialog({
  question,
  onClose,
}: {
  question: Question
  onClose: () => void
}) {
  const qrRef = useRef<SVGSVGElement>(null)
  const [copied, setCopied] = useState(false)
  const viewerUrl = `${window.location.origin}/q/${question.id}`

  async function copyLink() {
    await navigator.clipboard.writeText(viewerUrl)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1800)
  }

  function downloadQr() {
    if (!qrRef.current) return
    const source = new XMLSerializer().serializeToString(qrRef.current)
    const url = URL.createObjectURL(
      new Blob([source], { type: 'image/svg+xml;charset=utf-8' }),
    )
    const link = document.createElement('a')
    link.href = url
    link.download = `poll-${question.id}-qr.svg`
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section
        aria-labelledby="share-title"
        aria-modal="true"
        className="modal share-dialog"
        role="dialog"
      >
        <div className="modal-heading">
          <div>
            <span className="eyebrow">QR для эфира</span>
            <h2 id="share-title">{question.name}</h2>
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

        <div className="share-content">
          <div className="qr-card">
            <QRCodeSVG
              bgColor="#ffffff"
              fgColor="#171a2b"
              includeMargin
              level="H"
              ref={qrRef}
              size={224}
              value={viewerUrl}
            />
            <span>Наведите камеру телефона</span>
          </div>

          <div className="share-details">
            <div className="share-status">
              <span className={`status status-${question.effective_status}`}>
                {statusLabels[question.effective_status]}
              </span>
              {question.show_time && (
                <span>
                  {new Date(question.show_time).toLocaleString()} ·{' '}
                  {question.duration_seconds} сек.
                </span>
              )}
            </div>

            <div>
              <span className="share-label">Ссылка для зрителей</span>
              <div className="share-link">
                <input aria-label="Ссылка для зрителей" readOnly value={viewerUrl} />
                <button
                  className="primary-button"
                  onClick={() => void copyLink()}
                  type="button"
                >
                  {copied ? 'Скопировано ✓' : 'Копировать'}
                </button>
              </div>
            </div>

            <div className="share-actions">
              <button
                className="secondary-button"
                onClick={downloadQr}
                type="button"
              >
                Скачать QR
              </button>
              <a
                className="secondary-button"
                href={viewerUrl}
                rel="noreferrer"
                target="_blank"
              >
                Открыть форму ↗
              </a>
            </div>

            <p className="share-note">
              QR ведёт прямо на форму. Голосование откроется автоматически в
              заданное время и закроется по длительности эфира.
            </p>
          </div>
        </div>
      </section>
    </div>
  )
}
