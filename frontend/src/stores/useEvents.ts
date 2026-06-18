import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { AgentEvent } from '@/types'

export const useEvents = defineStore('events', () => {
  const events = ref<AgentEvent[]>([])
  const isStreaming = ref(false)

  const addEvent = (event: AgentEvent) => {
    events.value.push(event)
  }

  const clearEvents = () => {
    events.value = []
  }

  const setStreaming = (streaming: boolean) => {
    isStreaming.value = streaming
  }

  return {
    events,
    isStreaming,
    addEvent,
    clearEvents,
    setStreaming,
  }
})
