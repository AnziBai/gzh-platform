import client from './client'
import type { ApiResponse } from './client'

export interface Article {
  id: number | null
  title: string
  slug: string
  file_path: string
  status: string
  media_id?: string | null
  word_count: number | null
  image_count: number | null
  created_at: string | null
  updated_at: string | null
  content?: string
  frontmatter?: Record<string, unknown>
}

export interface TaskResponse {
  task_id: string
}

export interface Task {
  id: string
  type: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress: number
  message: string
  result: Record<string, unknown> | null
  error: string | null
  meta: Record<string, unknown>
  created_at: string
  updated_at: string
}

export async function getArticles(): Promise<Article[]> {
  const response = await client.get<ApiResponse<Article[]>>('/articles')
  return response.data.data
}

export async function getArticleBySlug(slug: string): Promise<Article> {
  const response = await client.get<ApiResponse<Article>>(`/articles/by-slug/${encodeURIComponent(slug)}`)
  return response.data.data
}

export async function generateArticle(topic: string, benchmarkSlug?: string): Promise<TaskResponse> {
  const response = await client.post<ApiResponse<TaskResponse>>('/articles/generate', {
    topic,
    benchmark_slug: benchmarkSlug,
  })
  return response.data.data
}

export async function publishArticle(slug: string): Promise<TaskResponse> {
  const response = await client.post<ApiResponse<TaskResponse>>(`/articles/${encodeURIComponent(slug)}/publish`)
  return response.data.data
}

export async function deleteArticle(id: number): Promise<void> {
  await client.delete(`/articles/${id}`)
}

export async function getTask(taskId: string): Promise<Task> {
  const response = await client.get<ApiResponse<Task>>(`/tasks/${taskId}`)
  return response.data.data
}
