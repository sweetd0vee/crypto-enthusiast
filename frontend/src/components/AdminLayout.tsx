import type { ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { LogoutIcon } from './Icons'

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
        <button
          aria-label="Выйти"
          className="logout-button"
          onClick={logout}
          title="Выйти"
          type="button"
        >
          <LogoutIcon />
        </button>
      </header>
      {children}
    </div>
  )
}
