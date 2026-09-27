import { type FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { setAdminToken } from '../adminAuth'

export function LoginPage() {
  const navigate = useNavigate()
  const [token, setToken] = useState('')

  function login(event: FormEvent) {
    event.preventDefault()
    if (!token.trim()) return
    setAdminToken(token.trim())
    navigate('/admin', { replace: true })
  }

  return (
    <main className="login-shell">
      <form className="panel login-card" onSubmit={login}>
        <span className="eyebrow">Управление опросами</span>
        <h1>Вход в админку</h1>
        <label>
          Токен администратора
          <input
            autoFocus
            onChange={(event) => setToken(event.target.value)}
            placeholder="Введите токен"
            type="password"
            value={token}
          />
        </label>
        <button className="primary-button" type="submit">
          Войти
        </button>
      </form>
    </main>
  )
}
