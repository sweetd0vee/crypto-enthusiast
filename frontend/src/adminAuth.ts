const ADMIN_TOKEN_KEY = 'adminToken'

/** Прочитать токен админки из sessionStorage. null — ещё не логинились. */
export function getAdminToken(): string | null {
  return sessionStorage.getItem(ADMIN_TOKEN_KEY)
}

/** Сохранить токен на время вкладки. После закрытия браузера пропадёт. */
export function setAdminToken(token: string): void {
  sessionStorage.setItem(ADMIN_TOKEN_KEY, token)
}

/** Сбросить токен после 401, чтобы снова показать форму логина. */
export function clearAdminToken(): void {
  sessionStorage.removeItem(ADMIN_TOKEN_KEY)
}
