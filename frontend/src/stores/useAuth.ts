import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'

// Use Vite's /api proxy in development so authentication remains same-origin
// even when Vite falls back from port 5173 to 5174.
const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

interface User {
  id: number
  username: string
  email: string
  is_active: boolean
  is_admin: boolean
  created_at: string
}

interface LoginCredentials {
  username: string
  password: string
}

interface RegisterData {
  username: string
  email: string
  password: string
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const token = ref<string | null>(localStorage.getItem('access_token'))
  const isAuthenticated = ref<boolean>(!!token.value)

  const login = async (credentials: LoginCredentials) => {
    const response = await axios.post(`${API_BASE}/auth/login`, credentials)
    token.value = response.data.access_token
    user.value = response.data.user
    isAuthenticated.value = true
    localStorage.setItem('access_token', response.data.access_token)
    localStorage.setItem('user', JSON.stringify(response.data.user))
  }

  const register = async (data: RegisterData) => {
    const response = await axios.post(`${API_BASE}/auth/register`, data)
    token.value = response.data.access_token
    user.value = response.data.user
    isAuthenticated.value = true
    localStorage.setItem('access_token', response.data.access_token)
    localStorage.setItem('user', JSON.stringify(response.data.user))
  }

  const logout = () => {
    token.value = null
    user.value = null
    isAuthenticated.value = false
    localStorage.removeItem('access_token')
    localStorage.removeItem('user')
  }

  const loadUser = () => {
    const storedUser = localStorage.getItem('user')
    const storedToken = localStorage.getItem('access_token')
    if (storedUser && storedToken) {
      try {
        user.value = JSON.parse(storedUser)
        token.value = storedToken
        isAuthenticated.value = true
      } catch {
        logout()
      }
    }
  }

  return {
    user,
    token,
    isAuthenticated,
    login,
    register,
    logout,
    loadUser
  }
})
