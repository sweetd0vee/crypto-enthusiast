import { statusLabels } from '../displayFormatting'
import type { EffectiveStatus } from '../types'

export function StatusBadge({ status }: { status: EffectiveStatus }) {
  return (
    <span className={`status status-${status}`}>
      {statusLabels[status]}
    </span>
  )
}
