import client from './client'
import type { ApiResponse } from './client'
import type { Benchmark } from './benchmarks'

export interface KnowledgeFile {
  id: number
  filename: string
  original_filename: string
  file_type: string
  file_path: string
  status: 'ready' | 'processing' | 'failed'
  chunk_count: number
  error_message: string | null
  created_at: string | null
  updated_at: string | null
}

export interface KnowledgeChunk {
  id: number
  file_id: number
  chunk_index: number
  title: string | null
  content: string
  content_hash: string
  keywords: string[]
  reason?: string | null
  score?: number | null
  created_at: string | null
}

export interface KnowledgeRecommendation {
  knowledge_chunks: KnowledgeChunk[]
  fact_materials: Benchmark[]
  reference_articles: Benchmark[]
  warnings: string[]
}

export async function getKnowledgeFiles(): Promise<KnowledgeFile[]> {
  const response = await client.get<ApiResponse<KnowledgeFile[]>>('/knowledge/files')
  return response.data.data
}

export async function uploadKnowledgeFile(file: File): Promise<KnowledgeFile> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await client.post<ApiResponse<KnowledgeFile>>('/knowledge/files', formData)
  return response.data.data
}

export async function deleteKnowledgeFile(id: number): Promise<{ deleted: boolean }> {
  const response = await client.delete<ApiResponse<{ deleted: boolean }>>(`/knowledge/files/${id}`)
  return response.data.data
}

export async function recommendKnowledge(data: {
  topic: string
  hotspot_title?: string
  knowledge_file_ids?: number[]
  limit?: number
}): Promise<KnowledgeRecommendation> {
  const response = await client.post<ApiResponse<KnowledgeRecommendation>>('/knowledge/recommend', data)
  return response.data.data
}
