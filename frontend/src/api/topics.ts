import client from './client'
import type { ApiResponse } from './client'

export interface Topic {
  id: number
  title: string
  platform: string
  source_url: string | null
  hot_value: number | null
  relevance_score: number | null
  relevance_reason: string | null
  status: string  // new | selected | used | dismissed
  brief: TopicBrief | null
  material_ids: number[]
  reference_article_slug: string | null
  generated_article_id: number | null
  discovered_at: string | null
}

export interface TopicBrief {
  recommended_title?: string
  title_angles?: string[]
  audience_pain_points?: string[]
  outline?: string[]
  usable_materials?: string[]
  risk_notes?: string[]
}

export async function getTopics(status?: string): Promise<Topic[]> {
  const params = status ? { status } : {}
  const response = await client.get<ApiResponse<Topic[]>>('/topics', { params })
  return response.data.data
}

export async function scrapeTopics(platform?: string): Promise<{ task_id: string }> {
  const response = await client.post<ApiResponse<{ task_id: string }>>('/topics/scrape', {
    platform,
  })
  return response.data.data
}

export async function selectTopic(id: number): Promise<Topic> {
  const response = await client.post<ApiResponse<Topic>>(`/topics/${id}/select`)
  return response.data.data
}

export async function dismissTopic(id: number): Promise<Topic> {
  const response = await client.post<ApiResponse<Topic>>(`/topics/${id}/dismiss`)
  return response.data.data
}

export async function generateTopicBrief(
  id: number,
  data: { material_ids?: number[]; reference_article_slug?: string | null },
): Promise<{ task_id: string }> {
  const response = await client.post<ApiResponse<{ task_id: string }>>(`/topics/${id}/brief`, data)
  return response.data.data
}

export async function generateTopicArticle(id: number): Promise<{ task_id: string }> {
  const response = await client.post<ApiResponse<{ task_id: string }>>(`/topics/${id}/generate`)
  return response.data.data
}
