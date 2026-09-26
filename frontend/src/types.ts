export type ApiErrorCode =
  | 'unauthorized'
  | 'not_found'
  | 'already_voted'
  | 'options_locked'
  | 'delete_forbidden'
  | 'window_closed'
  | 'window_not_started'
  | 'not_published'
  | 'invalid_option'
  | 'invalid_body'
  | 'unavailable'

export interface ApiErrorBody {
  error: ApiErrorCode
  message: string
}

export interface OptionInput {
  key: string
  label: string
}

export interface PublicQuestion {
  id: number
  name: string
  closes_at: string
  options: OptionInput[]
}

export type QuestionStatus = 'draft' | 'published' | 'cancelled'
export type EffectiveStatus =
  | QuestionStatus
  | 'scheduled'
  | 'live'
  | 'closed'

export interface QuestionInput {
  name: string
  status: QuestionStatus
  show_time: string | null
  duration_seconds: number
  options: OptionInput[]
}

export interface Question extends QuestionInput {
  id: number
  effective_status: EffectiveStatus
  options: Array<OptionInput & { position: number }>
}

export interface OptionCount extends OptionInput {
  count: number
}

export interface QuestionResult {
  question_id: number
  name: string
  effective_status: EffectiveStatus
  total: number
  counts: OptionCount[]
}
