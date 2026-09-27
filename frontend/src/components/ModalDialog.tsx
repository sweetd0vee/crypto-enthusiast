import type { ReactNode } from 'react'

export function ModalDialog({
  children,
  className = '',
  eyebrow,
  onClose,
  title,
  titleId,
}: {
  children: ReactNode
  className?: string
  eyebrow: string
  onClose: () => void
  title: string
  titleId: string
}) {
  return (
    <div className="modal-backdrop" role="presentation">
      <section
        aria-labelledby={titleId}
        aria-modal="true"
        className={`modal ${className}`.trim()}
        role="dialog"
      >
        <div className="modal-heading">
          <div>
            <span className="eyebrow">{eyebrow}</span>
            <h2 id={titleId}>{title}</h2>
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
        {children}
      </section>
    </div>
  )
}
