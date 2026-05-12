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
  material_type: 'reference_article' | 'fact_material'
  source_kind: string | null
  source_hash: string | null
  classification_reason: string | null
  approved_from_candidate_id: number | null
  created_at: string | null
}

export async function getBenchmarks(materialType?: string): Promise<Benchmark[]> {
  const params = materialType ? { material_type: materialType } : {}
  const response = await client.get<ApiResponse<Benchmark[]>>('/benchmarks', { params })
  return response.data.data
}

export async function createBenchmark(data: {
  title: string
  content: string
  platform?: string
  source_url?: string
  material_type?: 'reference_article' | 'fact_material'
}): Promise<Benchmark> {
  const response = await client.post<ApiResponse<Benchmark>>('/benchmarks', data)
  return response.data.data
}

export async function deleteBenchmark(id: number): Promise<void> {
  await client.delete(`/benchmarks/${id}`)
}

export async function updateBenchmark(
  id: number,
  data: Partial<Pick<Benchmark, 'title' | 'platform' | 'source_url' | 'material_type'>>,
): Promise<Benchmark> {
  const response = await client.put<ApiResponse<Benchmark>>(`/benchmarks/${id}`, data)
  return response.data.data
}

export async function recommendBenchmarks(topic: string): Promise<{
  fact_materials: Benchmark[]
  reference_articles: Benchmark[]
}> {
  const response = await client.get<ApiResponse<{
    fact_materials: Benchmark[]
    reference_articles: Benchmark[]
  }>>('/benchmarks/recommend', { params: { topic } })
  return response.data.data
}
