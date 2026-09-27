import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { getAdminToken } from '../adminAuth'

export function RequireAuth({ children }: { children: ReactNode }) {
  return getAdminToken() ? (
    children
  ) : (
    <Navigate replace to="/admin/login" />
  )
}
