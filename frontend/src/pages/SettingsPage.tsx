import { useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Form, Input, List, Select, Space, Spin, Tag, Typography, message } from 'antd'
import {
  ApiOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ReloadOutlined,
  SaveOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { getSettings, getSettingsDiagnostics, testAiSettings, testWechatSettings, updateSettings } from '../api/settings'
import type { SettingsUpdate } from '../api/settings'

const { Text } = Typography

interface SettingsFormValues {
  wechat_app_id: string
  wechat_app_secret?: string
  ai_provider: string
  ai_base_url?: string
  ai_api_key?: string
  ai_model?: string
  claude_bin?: string
}

export default function SettingsPage() {
  const [form] = Form.useForm<SettingsFormValues>()
  const [messageApi, contextHolder] = message.useMessage()
  const queryClient = useQueryClient()

  const { data, isLoading, error } = useQuery({
    queryKey: ['settings'],
    queryFn: getSettings,
  })

  const diagnostics = useQuery({
    queryKey: ['settings-diagnostics'],
    queryFn: getSettingsDiagnostics,
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
      claude_bin: data.ai_writer.claude_bin,
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

  const handleFinish = (values: SettingsFormValues) => {
    const payload: SettingsUpdate = {
      wechat: {
        app_id: values.wechat_app_id,
      },
      ai_writer: {
        provider: values.ai_provider,
        base_url: values.ai_base_url,
        model: values.ai_model,
        claude_bin: values.claude_bin,
      },
    }
    if (values.wechat_app_secret?.trim()) {
      payload.wechat!.app_secret = values.wechat_app_secret.trim()
    }
    if (values.ai_api_key?.trim()) {
      payload.ai_writer!.api_key = values.ai_api_key.trim()
    }
    saveMutation.mutate(payload)
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
            <Alert type="error" showIcon message={(diagnostics.error as Error).message} />
          ) : (
            <List
              size="small"
              dataSource={diagnostics.data?.checks ?? []}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta
                    avatar={
                      item.ok ? (
                        <CheckCircleOutlined style={{ color: '#389e0d' }} />
                      ) : (
                        <CloseCircleOutlined style={{ color: '#d48806' }} />
                      )
                    }
                    title={
                      <Space>
                        <Text>{item.label}</Text>
                        <Tag color={item.ok ? 'green' : 'warning'}>{item.ok ? 'OK' : '待处理'}</Tag>
                      </Space>
                    }
                    description={
                      <div>
                        <div>{item.detail}</div>
                        {!item.ok && item.action && <Text type="secondary">{item.action}</Text>}
                      </div>
                    }
                  />
                </List.Item>
              )}
            />
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
            <Button
              icon={<ThunderboltOutlined />}
              onClick={() => aiTestMutation.mutate()}
              loading={aiTestMutation.isPending}
            >
              测试 AI 连接
            </Button>
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
