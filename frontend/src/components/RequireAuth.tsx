import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'

export function RequireAuth({ children }: { children: ReactNode }) {
  return sessionStorage.getItem('adminToken') ? (
    children
  ) : (
    <Navigate replace to="/admin/login" />
  )
}
