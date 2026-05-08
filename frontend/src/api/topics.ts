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
  discovered_at: string | null
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
