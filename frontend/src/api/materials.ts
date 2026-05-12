import client from './client'
import type { ApiResponse } from './client'

export interface MaterialCandidate {
  id: number
  title: string
  content: string
  source_url: string | null
  platform: string
  suggested_material_type: 'reference_article' | 'fact_material'
  status: 'candidate' | 'approved' | 'rejected' | 'failed'
  confidence: number | null
  classification_reason: string | null
  source_kind: string | null
  topic_id: number | null
  article_id: number | null
  source_hash: string | null
  created_at: string | null
  updated_at: string | null
}

export async function getMaterialCandidates(status?: string): Promise<MaterialCandidate[]> {
  const response = await client.get<ApiResponse<MaterialCandidate[]>>('/materials/candidates', {
    params: status ? { status } : {},
  })
  return response.data.data
}

export async function collectMaterials(data: {
  source?: 'topics' | 'articles' | 'hot_articles' | 'search'
  topic_ids?: number[]
  keyword?: string
}): Promise<{ task_id: string }> {
  const response = await client.post<ApiResponse<{ task_id: string }>>('/materials/collect', data)
  return response.data.data
}

export async function approveMaterialCandidate(
  id: number,
  materialType?: 'reference_article' | 'fact_material',
): Promise<{ benchmark_id: number; deduplicated: boolean }> {
  const response = await client.post<ApiResponse<{ benchmark_id: number; deduplicated: boolean }>>(
    `/materials/candidates/${id}/approve`,
    { material_type: materialType },
  )
  return response.data.data
}

export async function rejectMaterialCandidate(id: number): Promise<{ candidate_id: number }> {
  const response = await client.post<ApiResponse<{ candidate_id: number }>>(`/materials/candidates/${id}/reject`)
  return response.data.data
}
