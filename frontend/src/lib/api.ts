import axios, { AxiosInstance, AxiosError } from 'axios'
import * as Sentry from '@sentry/nextjs'

const api: AxiosInstance = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  headers: {
    'Content-Type': 'application/json',
  },
})

// Add auth token to requests
api.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('authToken')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
  }
  return config
})

// Handle errors
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      // Redirect to login on unauthorized
      if (typeof window !== 'undefined') {
        localStorage.removeItem('authToken')
        window.location.href = '/auth/login'
      }
    }

    Sentry.captureException(error, {
      tags: {
        api_method: error.config?.method?.toUpperCase(),
        api_url: error.config?.url,
        status_code: error.response?.status?.toString() || '0',
      },
      extra: {
        request_data: error.config?.data,
        response_data: error.response?.data,
      },
    })

    return Promise.reject(error)
  }
)

export default api
