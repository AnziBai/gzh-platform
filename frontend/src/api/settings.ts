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
    preset_provider: string
    extra_body_json: string
    claude_bin: string
  }
  search: {
    provider: string
    base_url: string
    api_key_configured: boolean
  }
  directories: {
    gzhpublisher_root: string
    articles_dir: string
    benchmarks_dir: string
    assets_dir: string
    database_dir: string
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
    preset_provider?: string
    extra_body_json?: string
    claude_bin?: string
  }
  search?: {
    provider?: string
    api_key?: string
    base_url?: string
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

export interface DiagnosticCheck {
  ok: boolean
  label: string
  detail: string
  action: string
}

export interface DiagnosticsResult {
  ok: boolean
  checks: DiagnosticCheck[]
  setup_steps?: Array<{
    key: string
    title: string
    ok: boolean
    description: string
    action: string
  }>
  capabilities?: {
    can_generate_articles: boolean
    can_sync_wechat_data: boolean
    can_publish_drafts: boolean
    can_archive_outputs: boolean
  }
}

export async function getSettingsDiagnostics(): Promise<DiagnosticsResult> {
  const response = await client.get<ApiResponse<DiagnosticsResult>>('/settings/diagnostics')
  return response.data.data
}

export async function bootstrapSettings(rootDir?: string): Promise<{
  created: Record<string, string>
  next_steps: string[]
  diagnostics: DiagnosticsResult
}> {
  const response = await client.post<ApiResponse<{
    created: Record<string, string>
    next_steps: string[]
    diagnostics: DiagnosticsResult
  }>>('/settings/bootstrap', { root_dir: rootDir })
  return response.data.data
}

export interface ModelPreset {
  key: string
  name: string
  provider: string
  base_url: string
  recommended_models: string[]
  description: string
  extra_body_example?: Record<string, unknown>
}

export async function getModelPresets(): Promise<ModelPreset[]> {
  const response = await client.get<ApiResponse<ModelPreset[]>>('/settings/model-presets')
  return response.data.data
}
