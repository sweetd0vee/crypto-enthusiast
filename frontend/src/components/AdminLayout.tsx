import type { ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'

export function AdminLayout({ children }: { children: ReactNode }) {
  const navigate = useNavigate()

  function logout() {
    sessionStorage.removeItem('adminToken')
    navigate('/admin/login')
  }

  return (
    <div className="admin-shell">
      <header className="admin-header">
        <Link className="brand" to="/admin">
          <span className="brand-mark">Q</span>
          TV Poll
        </Link>
        <button className="text-button" onClick={logout} type="button">
          Выйти
        </button>
      </header>
      {children}
    </div>
  )
}
