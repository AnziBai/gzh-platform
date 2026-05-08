import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Button,
  Table,
  Tag,
  Modal,
  Form,
  Input,
  Select,
  Popconfirm,
  Spin,
  Alert,
  Empty,
  Typography,
  message,
} from 'antd'
import { PlusOutlined, DeleteOutlined, FileTextOutlined } from '@ant-design/icons'
import { getBenchmarks, createBenchmark, deleteBenchmark } from '../api/benchmarks'
import type { Benchmark } from '../api/benchmarks'
import type { ColumnsType } from 'antd/es/table'

const { Text } = Typography

const platformColors: Record<string, string> = {
  manual: 'default',
  toutiao: 'red',
  sina: 'orange',
  juejin: 'blue',
  eastmoney: 'cyan',
  xueqiu: 'green',
}

const platformLabels: Record<string, string> = {
  manual: '手动添加',
  toutiao: '今日头条',
  sina: '新浪财经',
  juejin: '掘金',
  eastmoney: '东方财富',
  xueqiu: '雪球',
}

interface FormValues {
  title: string
  content: string
  platform: string
  source_url?: string
}

export default function BenchmarksPage() {
  const queryClient = useQueryClient()
  const [modalOpen, setModalOpen] = useState(false)
  const [pasteModalOpen, setPasteModalOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [pasteContent, setPasteContent] = useState('')
  const [pastePlatform, setPastePlatform] = useState('manual')
  const [form] = Form.useForm<FormValues>()
  const [messageApi, contextHolder] = message.useMessage()

  const { data: benchmarks, isLoading, error } = useQuery({
    queryKey: ['benchmarks'],
    queryFn: getBenchmarks,
  })

  const handleAdd = async (values: FormValues) => {
    setSubmitting(true)
    try {
      await createBenchmark({
        title: values.title,
        content: values.content,
        platform: values.platform,
        source_url: values.source_url || undefined,
      })
      messageApi.success('素材添加成功')
      setModalOpen(false)
      form.resetFields()
      queryClient.invalidateQueries({ queryKey: ['benchmarks'] })
    } catch (e) {
      messageApi.error(`添加失败：${(e as Error).message}`)
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await deleteBenchmark(id)
      messageApi.success('已删除')
      queryClient.invalidateQueries({ queryKey: ['benchmarks'] })
    } catch (e) {
      messageApi.error(`删除失败：${(e as Error).message}`)
    }
  }

  const handleQuickPaste = async () => {
    const trimmed = pasteContent.trim()
    if (!trimmed) {
      messageApi.warning('请粘贴文章内容')
      return
    }
    // Auto-extract title: first non-empty line, strip markdown heading markers
    const lines = trimmed.split('\n').filter((l) => l.trim())
    const firstLine = lines[0]?.replace(/^#+\s*/, '').trim() || '未命名素材'
    setSubmitting(true)
    try {
      await createBenchmark({
        title: firstLine.slice(0, 100),
        content: trimmed,
        platform: pastePlatform,
      })
      messageApi.success('爆款文章已保存')
      setPasteModalOpen(false)
      setPasteContent('')
      setPastePlatform('manual')
      queryClient.invalidateQueries({ queryKey: ['benchmarks'] })
    } catch (e) {
      messageApi.error(`保存失败：${(e as Error).message}`)
    } finally {
      setSubmitting(false)
    }
  }

  const columns: ColumnsType<Benchmark> = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
      render: (title: string) => (
        <Text style={{ fontSize: 13 }}>{title}</Text>
      ),
    },
    {
      title: '平台',
      dataIndex: 'platform',
      key: 'platform',
      width: 110,
      render: (platform: string) => (
        <Tag color={platformColors[platform] ?? 'default'} style={{ margin: 0 }}>
          {platformLabels[platform] ?? platform}
        </Tag>
      ),
    },
    {
      title: '相关度',
      dataIndex: 'relevance_score',
      key: 'relevance_score',
      width: 90,
      render: (score: number | null) =>
        score != null ? (
          <Text style={{ fontSize: 13 }}>{score.toFixed(2)}</Text>
        ) : (
          <Text type="secondary" style={{ fontSize: 12 }}>—</Text>
        ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (val: string | null) =>
        val ? (
          <Text type="secondary" style={{ fontSize: 12 }}>
            {new Date(val).toLocaleString('zh-CN', {
              year: 'numeric',
              month: '2-digit',
              day: '2-digit',
              hour: '2-digit',
              minute: '2-digit',
            })}
          </Text>
        ) : (
          <Text type="secondary" style={{ fontSize: 12 }}>—</Text>
        ),
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_: unknown, record: Benchmark) =>
        record.id != null ? (
          <Popconfirm
            title="确认删除该素材？"
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            onConfirm={() => handleDelete(record.id as number)}
          >
            <Button type="text" danger icon={<DeleteOutlined />} size="small" />
          </Popconfirm>
        ) : null,
    },
  ]

  if (isLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 80 }}>
        <Spin size="large" />
      </div>
    )
  }

  if (error) {
    return (
      <Alert type="error" message="加载失败" description={(error as Error).message} showIcon />
    )
  }

  const total = benchmarks?.length ?? 0

  return (
    <>
      {contextHolder}

      {/* 统计卡片 */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 16 }}>
        <div
          style={{
            background: '#fff',
            borderRadius: 8,
            boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
            padding: '16px 24px',
            minWidth: 140,
          }}
        >
          <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
            总素材数
          </Text>
          <Text style={{ fontSize: 24, fontWeight: 600, lineHeight: 1 }}>{total}</Text>
        </div>
      </div>

      {/* 列表卡片 */}
      <div
        style={{
          background: '#fff',
          borderRadius: 8,
          boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
          padding: 16,
        }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 16,
          }}
        >
          <Text strong style={{ fontSize: 15 }}>
            素材列表
          </Text>
          <div style={{ display: 'flex', gap: 8 }}>
            <Button
              type="primary"
              icon={<FileTextOutlined />}
              onClick={() => setPasteModalOpen(true)}
            >
              粘贴爆款文章
            </Button>
            <Button
              icon={<PlusOutlined />}
              onClick={() => setModalOpen(true)}
            >
              手动添加
            </Button>
          </div>
        </div>

        <Table<Benchmark>
          dataSource={benchmarks ?? []}
          columns={columns}
          rowKey={(record) => (record.id != null ? String(record.id) : record.title ?? '')}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          size="middle"
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                  <span>
                    暂无素材，
                    <Button type="link" style={{ padding: 0 }} onClick={() => setModalOpen(true)}>
                      点击添加素材
                    </Button>
                  </span>
                }
              />
            ),
          }}
        />
      </div>

      {/* 快速粘贴爆款文章弹窗 */}
      <Modal
        title="粘贴爆款文章"
        open={pasteModalOpen}
        onCancel={() => {
          setPasteModalOpen(false)
          setPasteContent('')
        }}
        footer={null}
        width={680}
        destroyOnHidden
      >
        <div style={{ marginBottom: 12 }}>
          <Text type="secondary" style={{ fontSize: 13 }}>
            粘贴完整文章内容，标题会自动从第一行提取。保存后可在文章生成时作为参考素材。
          </Text>
        </div>
        <div style={{ marginBottom: 12 }}>
          <Text strong style={{ fontSize: 13, display: 'block', marginBottom: 4 }}>来源平台</Text>
          <div style={{ display: 'flex', gap: 8 }}>
            {[
              { value: 'manual', label: '其他' },
              { value: 'toutiao', label: '今日头条' },
              { value: 'sina', label: '新浪财经' },
              { value: 'juejin', label: '掘金' },
              { value: 'eastmoney', label: '东方财富' },
              { value: 'xueqiu', label: '雪球' },
            ].map((opt) => (
              <Button
                key={opt.value}
                size="small"
                type={pastePlatform === opt.value ? 'primary' : 'default'}
                onClick={() => setPastePlatform(opt.value)}
              >
                {opt.label}
              </Button>
            ))}
          </div>
        </div>
        <Input.TextArea
          rows={14}
          placeholder={"在这里粘贴完整文章内容...\n\n标题会自动从第一行提取，例如：\nK线经典口诀｜新手炒股避坑指南\n\n正文内容..."}
          value={pasteContent}
          onChange={(e) => setPasteContent(e.target.value)}
          style={{ fontSize: 13, lineHeight: 1.7 }}
          autoFocus
        />
        {pasteContent.trim() && (
          <div style={{ marginTop: 8, padding: '6px 10px', background: '#f6ffed', borderRadius: 4, border: '1px solid #b7eb8f' }}>
            <Text style={{ fontSize: 12, color: '#389e0d' }}>
              标题将提取为：{pasteContent.trim().split('\n')[0]?.replace(/^#+\s*/, '').trim().slice(0, 100)}
            </Text>
          </div>
        )}
        <div style={{ marginTop: 16, textAlign: 'right' }}>
          <Button
            style={{ marginRight: 8 }}
            onClick={() => {
              setPasteModalOpen(false)
              setPasteContent('')
            }}
          >
            取消
          </Button>
          <Button type="primary" loading={submitting} onClick={handleQuickPaste}>
            保存
          </Button>
        </div>
      </Modal>

      {/* 添加素材弹窗 */}
      <Modal
        title="添加素材"
        open={modalOpen}
        onCancel={() => {
          setModalOpen(false)
          form.resetFields()
        }}
        footer={null}
        width={560}
        destroyOnHidden
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleAdd}
          initialValues={{ platform: 'manual' }}
          style={{ marginTop: 8 }}
        >
          <Form.Item
            label="标题"
            name="title"
            rules={[{ required: true, message: '请输入标题' }]}
          >
            <Input placeholder="素材标题" />
          </Form.Item>

          <Form.Item label="平台" name="platform">
            <Select
              options={[
                { value: 'manual', label: '手动添加' },
                { value: 'toutiao', label: '今日头条' },
                { value: 'juejin', label: '掘金' },
                { value: 'eastmoney', label: '东方财富' },
                { value: 'xueqiu', label: '雪球' },
              ]}
            />
          </Form.Item>

          <Form.Item label="来源 URL（可选）" name="source_url">
            <Input placeholder="https://..." />
          </Form.Item>

          <Form.Item
            label="正文内容"
            name="content"
            rules={[{ required: true, message: '请粘贴文章内容' }]}
          >
            <Input.TextArea
              rows={8}
              placeholder="粘贴文章正文内容"
              style={{ fontFamily: 'inherit', fontSize: 13 }}
            />
          </Form.Item>

          <Form.Item style={{ marginBottom: 0, textAlign: 'right' }}>
            <Button
              style={{ marginRight: 8 }}
              onClick={() => {
                setModalOpen(false)
                form.resetFields()
              }}
            >
              取消
            </Button>
            <Button type="primary" htmlType="submit" loading={submitting}>
              添加
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}
