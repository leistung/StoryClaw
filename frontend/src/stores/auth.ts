import { create } from 'zustand'
import api, { TOKEN_KEY } from '@/lib/http'
import type { User } from '@/types'

interface AuthState {
  user: User | null
  token: string | null
  hydrated: boolean
  setAuth: (user: User, token: string) => void
  logout: () => void
  fetchMe: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  token: localStorage.getItem(TOKEN_KEY),
  hydrated: false,
  setAuth: (user, token) => {
    localStorage.setItem(TOKEN_KEY, token)
    set({ user, token, hydrated: true })
  },
  logout: () => {
    localStorage.removeItem(TOKEN_KEY)
    set({ user: null, token: null })
  },
  fetchMe: async () => {
    const token = get().token
    if (!token) {
      set({ hydrated: true })
      return
    }
    try {
      const res = await api.get<User>('/auth/me')
      set({ user: res.data, hydrated: true })
    } catch {
      localStorage.removeItem(TOKEN_KEY)
      set({ user: null, token: null, hydrated: true })
    }
  },
}))
