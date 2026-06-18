import { ref } from 'vue'
import type { ErrorResponse } from '@/types'

export function useErrorHandler() {
  const error = ref<string | null>(null)
  const isError = ref(false)

  const handleError = (err: any) => {
    isError.value = true

    if (err.response?.data) {
      const errorData = err.response.data as ErrorResponse
      error.value = errorData.message || 'An error occurred'
    } else if (err.message) {
      error.value = err.message
    } else {
      error.value = 'An unexpected error occurred'
    }

    console.error('Error:', err)
  }

  const clearError = () => {
    error.value = null
    isError.value = false
  }

  return {
    error,
    isError,
    handleError,
    clearError,
  }
}
