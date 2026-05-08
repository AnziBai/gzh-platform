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
    if (error?.response?.status === 502) {
      return Promise.reject(
        new Error('后端服务不可达，请确认 Flask 后端已启动且 5001 端口未被防火墙拦截')
      )
    }
    if (error?.code === 'ERR_NETWORK') {
      return Promise.reject(new Error('无法连接后端服务，请确认 Flask 后端已启动'))
    }
    return Promise.reject(error)
  }
)

export default client
