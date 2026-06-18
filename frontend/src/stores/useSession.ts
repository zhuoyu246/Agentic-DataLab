import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Session } from '@/types'

export const useSession = defineStore('session', () => {
  const currentSession = ref<Session | null>(null)
  const sessions = ref<Session[]>([])

  const setCurrentSession = (session: Session | null) => {
    currentSession.value = session
  }

  const addSession = (session: Session) => {
    sessions.value.unshift(session)
  }

  const removeSession = (sessionId: string) => {
    sessions.value = sessions.value.filter(s => s.session_id !== sessionId)
    if (currentSession.value?.session_id === sessionId) {
      currentSession.value = null
    }
  }

  return {
    currentSession,
    sessions,
    setCurrentSession,
    addSession,
    removeSession,
  }
})
