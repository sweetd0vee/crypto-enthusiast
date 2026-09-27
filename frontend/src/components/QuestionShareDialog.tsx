import { useRef, useState } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import type { Question } from '../types'
import { ModalDialog } from './ModalDialog'
import { StatusBadge } from './StatusBadge'

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
    <ModalDialog
      className="share-dialog"
      eyebrow="QR для эфира"
      onClose={onClose}
      title={question.name}
      titleId="share-title"
    >
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
              <StatusBadge status={question.effective_status} />
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
    </ModalDialog>
  )
}
