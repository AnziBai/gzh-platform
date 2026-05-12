import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Form, Input, Progress, Select, Space, Spin, Tag, Typography, message } from 'antd'
import {
  ApiOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  FolderAddOutlined,
  ReloadOutlined,
  SaveOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { bootstrapSettings, getModelPresets, getSettings, getSettingsDiagnostics, testAiSettings, testWechatSettings, updateSettings } from '../api/settings'
import type { SettingsUpdate } from '../api/settings'

const { Text } = Typography

interface SettingsFormValues {
  wechat_app_id: string
  wechat_app_secret?: string
  ai_provider: string
  ai_base_url?: string
  ai_api_key?: string
  ai_model?: string
  ai_preset_provider?: string
  ai_extra_body_json?: string
  claude_bin?: string
  search_provider?: string
  search_base_url?: string
  search_api_key?: string
}

export default function SettingsPage() {
  const [form] = Form.useForm<SettingsFormValues>()
  const [messageApi, contextHolder] = message.useMessage()
  const [bootstrapRoot, setBootstrapRoot] = useState('')
  const queryClient = useQueryClient()

  const { data, isLoading, error } = useQuery({
    queryKey: ['settings'],
    queryFn: getSettings,
  })

  const diagnostics = useQuery({
    queryKey: ['settings-diagnostics'],
    queryFn: getSettingsDiagnostics,
  })

  const { data: modelPresets } = useQuery({
    queryKey: ['model-presets'],
    queryFn: getModelPresets,
  })

  useEffect(() => {
    if (!data) return
    form.setFieldsValue({
      wechat_app_id: data.wechat.app_id,
      wechat_app_secret: '',
      ai_provider: data.ai_writer.provider,
      ai_base_url: data.ai_writer.base_url,
      ai_api_key: '',
      ai_model: data.ai_writer.model,
      ai_preset_provider: data.ai_writer.preset_provider,
      ai_extra_body_json: data.ai_writer.extra_body_json,
      claude_bin: data.ai_writer.claude_bin,
      search_provider: data.search.provider,
      search_base_url: data.search.base_url,
      search_api_key: '',
    })
  }, [data, form])

  const saveMutation = useMutation({
    mutationFn: updateSettings,
    onSuccess: () => {
      messageApi.success('配置已保存')
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      queryClient.invalidateQueries({ queryKey: ['settings-diagnostics'] })
    },
    onError: (err: Error) => {
      messageApi.error(`保存失败：${err.message}`)
    },
  })

  const aiTestMutation = useMutation({
    mutationFn: testAiSettings,
    onSuccess: (result) => {
      messageApi.success(result.message || 'AI 连接正常')
    },
    onError: (err: Error) => {
      messageApi.error(`AI 连接失败：${err.message}`)
    },
  })

  const wechatTestMutation = useMutation({
    mutationFn: testWechatSettings,
    onSuccess: (result) => {
      messageApi.success(result.message || '微信公众号连接正常')
    },
    onError: (err: Error) => {
      messageApi.error(`微信公众号连接失败：${err.message}`)
    },
  })

  const bootstrapMutation = useMutation({
    mutationFn: () => bootstrapSettings(bootstrapRoot || undefined),
    onSuccess: () => {
      messageApi.success('首次部署目录已创建，目录配置已写入 .env')
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      queryClient.invalidateQueries({ queryKey: ['settings-diagnostics'] })
    },
    onError: (err: Error) => {
      messageApi.error(`首次部署向导失败：${err.message}`)
    },
  })

  const handleFinish = (values: SettingsFormValues) => {
    const payload: SettingsUpdate = {
      wechat: {
        app_id: values.wechat_app_id,
      },
      ai_writer: {
        provider: values.ai_provider,
        base_url: values.ai_base_url,
        model: values.ai_model,
        preset_provider: values.ai_preset_provider,
        extra_body_json: values.ai_extra_body_json,
        claude_bin: values.claude_bin,
      },
      search: {
        provider: values.search_provider,
        base_url: values.search_base_url,
      },
    }
    if (values.wechat_app_secret?.trim()) {
      payload.wechat!.app_secret = values.wechat_app_secret.trim()
    }
    if (values.ai_api_key?.trim()) {
      payload.ai_writer!.api_key = values.ai_api_key.trim()
    }
    if (values.search_api_key?.trim()) {
      payload.search!.api_key = values.search_api_key.trim()
    }
    saveMutation.mutate(payload)
  }

  const applyPreset = (presetKey?: string) => {
    const preset = modelPresets?.find((item) => item.key === presetKey)
    if (!preset) return
    form.setFieldsValue({
      ai_provider: preset.provider,
      ai_preset_provider: preset.key,
      ai_base_url: preset.base_url,
      ai_model: preset.recommended_models[0],
      ai_extra_body_json: preset.extra_body_example ? JSON.stringify(preset.extra_body_example, null, 2) : '',
    })
  }

  if (isLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 80 }}>
        <Spin size="large" />
      </div>
    )
  }

  if (error) {
    return <Alert type="error" title="加载失败" description={(error as Error).message} showIcon />
  }

  const setupSteps = diagnostics.data?.setup_steps ?? []
  const completedSetupSteps = setupSteps.filter((step) => step.ok).length
  const setupPercent = setupSteps.length ? Math.round((completedSetupSteps / setupSteps.length) * 100) : 0
  const capabilities = diagnostics.data?.capabilities
  const capabilityItems = [
    { key: 'can_generate_articles', label: '生成文章', ok: capabilities?.can_generate_articles },
    { key: 'can_sync_wechat_data', label: '同步公众号数据', ok: capabilities?.can_sync_wechat_data },
    { key: 'can_publish_drafts', label: '发布草稿', ok: capabilities?.can_publish_drafts },
    { key: 'can_archive_outputs', label: '归档记录', ok: capabilities?.can_archive_outputs },
  ]

  return (
    <>
      {contextHolder}
      <div style={{ maxWidth: 920 }}>
        <Text strong style={{ fontSize: 15, display: 'block', marginBottom: 16 }}>
          设置
        </Text>

        <Alert
          type="info"
          showIcon
          title="配置只保存在当前电脑的 backend/.env"
          description="密钥字段不会回显，留空表示保留现有密钥。保存后多数配置会即时生效；如果外部进程仍使用旧环境变量，再重启后端。"
          style={{ marginBottom: 16 }}
        />

        <Card
          size="small"
          title="开箱即用进度"
          style={{ marginBottom: 16, borderRadius: 8 }}
          extra={<Tag color={setupPercent === 100 ? 'green' : 'blue'}>{setupPercent}%</Tag>}
        >
          {diagnostics.isLoading ? (
            <Spin />
          ) : (
            <Space orientation="vertical" style={{ width: '100%' }} size={12}>
              <Progress percent={setupPercent} size="small" status={setupPercent === 100 ? 'success' : 'active'} />
              <Space wrap>
                {capabilityItems.map((item) => (
                  <Tag key={item.key} color={item.ok ? 'green' : 'default'}>
                    {item.label}{item.ok ? '可用' : '未就绪'}
                  </Tag>
                ))}
              </Space>
              <div>
                {setupSteps.map((step) => (
                  <div
                    key={step.key}
                    style={{
                      display: 'flex',
                      gap: 12,
                      padding: '10px 0',
                      borderBottom: '1px solid #f0f0f0',
                    }}
                  >
                    <div style={{ paddingTop: 2 }}>
                      {step.ok ? (
                        <CheckCircleOutlined style={{ color: '#389e0d' }} />
                      ) : (
                        <CloseCircleOutlined style={{ color: '#d48806' }} />
                      )}
                    </div>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <Space wrap>
                        <Text>{step.title}</Text>
                        <Tag color={step.ok ? 'green' : 'warning'}>{step.ok ? '完成' : '下一步'}</Tag>
                      </Space>
                      <div style={{ marginTop: 4 }}>{step.description}</div>
                      {!step.ok && (
                        <Text type="secondary" style={{ display: 'block', marginTop: 4 }}>
                          {step.action}
                        </Text>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </Space>
          )}
        </Card>

        <Card
          size="small"
          title="首次部署向导"
          style={{ marginBottom: 16, borderRadius: 8 }}
          extra={<Tag color="blue">只配置目录，不安装依赖</Tag>}
        >
          <Space orientation="vertical" style={{ width: '100%' }} size={12}>
            <Text type="secondary">
              一键创建文章、素材、资源和数据库目录，并写入 backend/.env。公众号密钥、AI Key 和 IP 白名单仍需要你按诊断提示填写。
            </Text>
            <Input
              value={bootstrapRoot}
              onChange={(event) => setBootstrapRoot(event.target.value)}
              placeholder={data?.directories.gzhpublisher_root || '例如 C:/gzh-content'}
            />
            <Button
              type="primary"
              icon={<FolderAddOutlined />}
              loading={bootstrapMutation.isPending}
              onClick={() => bootstrapMutation.mutate()}
            >
              创建目录并写入 .env
            </Button>
          </Space>
        </Card>

        <Card
          size="small"
          title="部署环境检查"
          style={{ marginBottom: 16, borderRadius: 8 }}
          extra={
            <Space>
              <Tag color={diagnostics.data?.ok ? 'green' : 'warning'}>
                {diagnostics.data?.ok ? '全部就绪' : '需要处理'}
              </Tag>
              <Button
                size="small"
                icon={<ReloadOutlined />}
                onClick={() => diagnostics.refetch()}
                loading={diagnostics.isFetching}
              >
                重新检查
              </Button>
            </Space>
          }
        >
          {diagnostics.isLoading ? (
            <Spin />
          ) : diagnostics.error ? (
            <Alert type="error" showIcon title={(diagnostics.error as Error).message} />
          ) : (
            <div>
              {(diagnostics.data?.checks ?? []).map((item) => (
                <div
                  key={item.label}
                  style={{
                    display: 'flex',
                    gap: 12,
                    padding: '10px 0',
                    borderBottom: '1px solid #f0f0f0',
                  }}
                >
                  <div style={{ paddingTop: 2 }}>
                    {item.ok ? (
                      <CheckCircleOutlined style={{ color: '#389e0d' }} />
                    ) : (
                      <CloseCircleOutlined style={{ color: '#d48806' }} />
                    )}
                  </div>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <Space wrap>
                      <Text>{item.label}</Text>
                      <Tag color={item.ok ? 'green' : 'warning'}>{item.ok ? 'OK' : '待处理'}</Tag>
                    </Space>
                    <div style={{ marginTop: 4, wordBreak: 'break-all' }}>{item.detail}</div>
                    {!item.ok && item.action && (
                      <Text type="secondary" style={{ display: 'block', marginTop: 4 }}>
                        {item.action}
                      </Text>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Form form={form} layout="vertical" onFinish={handleFinish}>
          <Card
            size="small"
            title="微信公众号数据"
            style={{ marginBottom: 16, borderRadius: 8 }}
            extra={
              <Tag color={data?.wechat.app_secret_configured ? 'green' : 'warning'}>
                {data?.wechat.app_secret_configured ? 'Secret 已配置' : 'Secret 未配置'}
              </Tag>
            }
          >
            <Form.Item label="WECHAT_APP_ID" name="wechat_app_id">
              <Input placeholder="公众号 AppID" />
            </Form.Item>
            <Form.Item label="WECHAT_APP_SECRET" name="wechat_app_secret">
              <Input.Password placeholder="留空则不修改现有 Secret" autoComplete="new-password" />
            </Form.Item>
            <Button
              icon={<ApiOutlined />}
              onClick={() => wechatTestMutation.mutate()}
              loading={wechatTestMutation.isPending}
            >
              测试微信公众号连接
            </Button>
          </Card>

          <Card
            size="small"
            title="AI 写作智能体"
            style={{ marginBottom: 16, borderRadius: 8 }}
            extra={
              <Tag color={data?.ai_writer.api_key_configured ? 'green' : 'default'}>
                {data?.ai_writer.api_key_configured ? 'API Key 已配置' : 'API Key 未配置'}
              </Tag>
            }
          >
            <Form.Item label="国内模型预设" name="ai_preset_provider">
              <Select
                allowClear
                placeholder="选择后自动填入 Base URL 和推荐模型"
                onChange={applyPreset}
                options={(modelPresets ?? []).map((preset) => ({
                  value: preset.key,
                  label: preset.name,
                }))}
              />
            </Form.Item>
            <Form.Item label="Provider" name="ai_provider">
              <Select
                options={[
                  { value: 'claude_cli', label: 'Claude CLI' },
                  { value: 'openai_compatible', label: 'OpenAI-compatible API' },
                ]}
              />
            </Form.Item>
            <Form.Item label="Claude CLI 路径" name="claude_bin">
              <Input placeholder="例如 C:/Users/me/AppData/Roaming/npm/claude.cmd" />
            </Form.Item>
            <Form.Item label="API Base URL" name="ai_base_url">
              <Input placeholder="例如 https://api.deepseek.com/v1" />
            </Form.Item>
            <Form.Item label="API Key" name="ai_api_key">
              <Input.Password placeholder="留空则不修改现有 API Key" autoComplete="new-password" />
            </Form.Item>
            <Form.Item label="Model" name="ai_model">
              <Input placeholder="例如 deepseek-chat / gpt-4.1 / glm-4-plus" />
            </Form.Item>
            <Form.Item label="AI_EXTRA_BODY_JSON" name="ai_extra_body_json">
              <Input.TextArea
                rows={4}
                placeholder={'例如 {"enable_thinking": false}，留空则不透传'}
                style={{ fontFamily: 'monospace', fontSize: 12 }}
              />
            </Form.Item>
            <Button
              icon={<ThunderboltOutlined />}
              onClick={() => aiTestMutation.mutate()}
              loading={aiTestMutation.isPending}
            >
              测试 AI 连接
            </Button>
          </Card>

          <Card
            size="small"
            title="搜索与热点源"
            style={{ marginBottom: 16, borderRadius: 8 }}
            extra={
              <Tag color={data?.search.api_key_configured ? 'green' : 'default'}>
                {data?.search.api_key_configured ? 'Search Key 已配置' : 'Search Key 未配置'}
              </Tag>
            }
          >
            <Form.Item label="SEARCH_PROVIDER" name="search_provider">
              <Select
                allowClear
                options={[
                  { value: 'custom', label: '自定义搜索 API' },
                ]}
              />
            </Form.Item>
            <Form.Item label="SEARCH_BASE_URL" name="search_base_url">
              <Input placeholder="返回 items/results，且每条结果包含 url/link/source_url" />
            </Form.Item>
            <Form.Item label="SEARCH_API_KEY" name="search_api_key">
              <Input.Password placeholder="留空则不修改现有 Search Key" autoComplete="new-password" />
            </Form.Item>
          </Card>

          <Space>
            <Button
              type="primary"
              htmlType="submit"
              icon={<SaveOutlined />}
              loading={saveMutation.isPending}
            >
              保存配置
            </Button>
          </Space>
        </Form>
      </div>
    </>
  )
}
