import { useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { clearAdminToken } from './adminAuth'
import { ApiError } from './api'

/** Если API ответил unauthorized — стереть токен и отправить на /admin/login. */
export function useAdminGuard() {
  const navigate = useNavigate()

  return useCallback(
    (error: unknown) => {
      if (!(error instanceof ApiError) || error.body.error !== 'unauthorized') {
        return false
      }
      clearAdminToken()
      navigate('/admin/login', { replace: true })
      return true
    },
    [navigate],
  )
}
