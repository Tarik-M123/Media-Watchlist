import { useState } from 'react'
import { clearToken, getToken, setToken } from './api'
import Dashboard from './components/Dashboard'
import Login from './components/Login'

const USER_KEY = 'mw_user'

// Both halves have to be present — a token with no cached user (or the
// reverse) would render a broken header, so treat that as signed out.
function loadUser() {
  if (!getToken()) return null
  try {
    return JSON.parse(localStorage.getItem(USER_KEY))
  } catch {
    return null
  }
}

export default function App() {
  const [user, setUser] = useState(loadUser)

  function handleAuth({ user, token }) {
    setToken(token)
    localStorage.setItem(USER_KEY, JSON.stringify(user))
    setUser(user)
  }

  function handleLogout() {
    clearToken()
    localStorage.removeItem(USER_KEY)
    setUser(null)
  }

  if (!user) return <Login onAuth={handleAuth} />
  return <Dashboard user={user} onLogout={handleLogout} />
}
