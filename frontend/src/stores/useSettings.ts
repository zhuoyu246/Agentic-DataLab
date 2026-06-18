import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useSettings = defineStore('settings', () => {
  const apiBaseUrl = ref(import.meta.env.VITE_API_URL || '/api/v1')
  const theme = ref<'light' | 'dark'>('light')
  const autoScroll = ref(true)

  const setTheme = (newTheme: 'light' | 'dark') => {
    theme.value = newTheme
    localStorage.setItem('theme', newTheme)
  }

  const toggleAutoScroll = () => {
    autoScroll.value = !autoScroll.value
  }

  // Load settings from localStorage
  const loadSettings = () => {
    const savedTheme = localStorage.getItem('theme') as 'light' | 'dark' | null
    if (savedTheme) theme.value = savedTheme
  }

  return {
    apiBaseUrl,
    theme,
    autoScroll,
    setTheme,
    toggleAutoScroll,
    loadSettings,
  }
})
