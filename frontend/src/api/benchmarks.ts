import client from './client'
import type { ApiResponse } from './client'

export interface Benchmark {
  id: number | null
  title: string
  platform: string
  source_url: string | null
  file_path: string | null
  structure_type: string | null
  relevance_score: number | null
  created_at: string | null
}

export async function getBenchmarks(): Promise<Benchmark[]> {
  const response = await client.get<ApiResponse<Benchmark[]>>('/benchmarks')
  return response.data.data
}

export async function createBenchmark(data: {
  title: string
  content: string
  platform?: string
  source_url?: string
}): Promise<Benchmark> {
  const response = await client.post<ApiResponse<Benchmark>>('/benchmarks', data)
  return response.data.data
}

export async function deleteBenchmark(id: number): Promise<void> {
  await client.delete(`/benchmarks/${id}`)
}
