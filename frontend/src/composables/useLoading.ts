import { ref } from 'vue'

export function useLoading() {
  const isLoading = ref(false)
  const loadingMessage = ref('')

  const startLoading = (message = 'Loading...') => {
    isLoading.value = true
    loadingMessage.value = message
  }

  const stopLoading = () => {
    isLoading.value = false
    loadingMessage.value = ''
  }

  const withLoading = async <T>(
    fn: () => Promise<T>,
    message?: string
  ): Promise<T> => {
    startLoading(message)
    try {
      return await fn()
    } finally {
      stopLoading()
    }
  }

  return {
    isLoading,
    loadingMessage,
    startLoading,
    stopLoading,
    withLoading,
  }
}
