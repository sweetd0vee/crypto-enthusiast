import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { RequireAuth } from './components/RequireAuth'
import { AdminPage } from './pages/AdminPage'
import { LoginPage } from './pages/LoginPage'
import { ResultsPage } from './pages/ResultsPage'
import { ViewerPage } from './pages/ViewerPage'
import './styles/public.css'
import './styles/admin.css'
import './styles/results.css'
import './styles/responsive.css'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/q/:id" element={<ViewerPage />} />
        <Route path="/admin/login" element={<LoginPage />} />
        <Route
          path="/admin"
          element={
            <RequireAuth>
              <AdminPage />
            </RequireAuth>
          }
        />
        <Route
          path="/admin/questions/:id"
          element={
            <RequireAuth>
              <ResultsPage />
            </RequireAuth>
          }
        />
        <Route path="*" element={<Navigate replace to="/admin" />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
