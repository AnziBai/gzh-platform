import client from './client'
import type { ApiResponse } from './client'

export interface Overview {
  total_articles: number
  published_articles: number
  draft_articles: number
  total_reads: number
  total_shares: number
  avg_read_per_article: number
  top_structure_types: Array<{
    structure_type: string
    count: number
    avg_reads: number
  }>
}

export interface ArticleAnalytics {
  id: number | null
  title: string
  slug: string
  status: string
  structure_type: string | null
  word_count: number | null
  publish_timestamp: string | null
  latest_read_count: number
  is_hot: boolean
  latest_share_count: number
  latest_like_count: number
  stats_count: number
  stats_fetched_at: string | null
}

export interface InsightItem {
  label: string
  avg_reads: number
  count: number
}

export type InsightDimension = 'structure_type' | 'word_count_bucket'

export async function getOverview(): Promise<Overview> {
  const response = await client.get<ApiResponse<Overview>>('/analytics/overview')
  return response.data.data
}

export async function getArticlesAnalytics(): Promise<ArticleAnalytics[]> {
  const response = await client.get<ApiResponse<ArticleAnalytics[]>>('/analytics/articles')
  return response.data.data
}

export interface FetchStatsResult {
  updated: number
  synced: number
  wechat_articles_found: number
  published_on_wechat: number
  errors: string[]
}

export async function fetchStats(): Promise<FetchStatsResult> {
  const response = await client.post<ApiResponse<FetchStatsResult>>('/analytics/fetch-stats')
  return response.data.data
}

export async function getInsights(dimension: InsightDimension): Promise<InsightItem[]> {
  const response = await client.get<ApiResponse<InsightItem[]>>('/analytics/insights', {
    params: { dimension },
  })
  return response.data.data
}
