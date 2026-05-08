import axios from 'axios'

const client = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
})

export interface ApiResponse<T> {
  status: number
  data: T
  message: string
}

client.interceptors.response.use(
  (response) => {
    const res = response.data as ApiResponse<unknown>
    if (res.status !== 0) {
      return Promise.reject(new Error(res.message || '请求失败'))
    }
    return response
  },
  (error) => {
    return Promise.reject(error)
  }
)

export default client
