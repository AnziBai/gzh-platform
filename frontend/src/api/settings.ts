import client from './client'
import type { ApiResponse } from './client'

export interface Settings {
  wechat: {
    app_id: string
    app_secret_configured: boolean
  }
  ai_writer: {
    provider: string
    base_url: string
    api_key_configured: boolean
    model: string
    claude_bin: string
  }
}

export interface SettingsUpdate {
  wechat?: {
    app_id?: string
    app_secret?: string
  }
  ai_writer?: {
    provider?: string
    base_url?: string
    api_key?: string
    model?: string
    claude_bin?: string
  }
}

export async function getSettings(): Promise<Settings> {
  const response = await client.get<ApiResponse<Settings>>('/settings')
  return response.data.data
}

export async function updateSettings(data: SettingsUpdate): Promise<Settings> {
  const response = await client.put<ApiResponse<Settings>>('/settings', data)
  return response.data.data
}

export interface ConnectionTestResult {
  ok: boolean
  provider?: string
  model?: string
  app_id?: string
  message: string
}

export async function testAiSettings(): Promise<ConnectionTestResult> {
  const response = await client.post<ApiResponse<ConnectionTestResult>>('/settings/test-ai')
  return response.data.data
}

export async function testWechatSettings(): Promise<ConnectionTestResult> {
  const response = await client.post<ApiResponse<ConnectionTestResult>>('/settings/test-wechat')
  return response.data.data
}
