import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  Button,
  Empty,
  Modal,
  Progress,
  Select,
  Spin,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import { CheckCircleOutlined, ClockCircleOutlined, SendOutlined } from '@ant-design/icons'
import { getArticles, publishArticle, rewriteForPublish } from '../api/articles'
import { getBenchmarks } from '../api/benchmarks'
import { useTaskStream } from '../hooks/useTaskStream'
import type { Article, Task } from '../api/articles'

const { Title, Text } = Typography

interface PublishState {
  taskId: string | null
  slug: string | null
  task: Task | null
}

const statusConfig: Record<string, { color: string; label: string }> = {
  draft: { color: 'default', label: '草稿' },
  published: { color: 'success', label: '已发布' },
  untracked: { color: 'warning', label: '未导入' },
}

export default function PublishPage() {
  const queryClient = useQueryClient()
  const [messageApi, contextHolder] = message.useMessage()
  const [publishState, setPublishState] = useState<PublishState>({ taskId: null, slug: null, task: null })
  const [modalOpen, setModalOpen] = useState(false)
  const [referenceBenchmarkId, setReferenceBenchmarkId] = useState<number | undefined>()
  const [taskMode, setTaskMode] = useState<'publish' | 'rewrite'>('publish')

  const { data: articles, isLoading, error } = useQuery({
    queryKey: ['articles'],
    queryFn: getArticles,
  })

  const { data: referenceMaterials } = useQuery({
    queryKey: ['benchmarks', 'reference_article'],
    queryFn: () => getBenchmarks('reference_article'),
  })

  const { task, logs } = useTaskStream({
    taskId: publishState.taskId,
    onComplete: (t) => {
      setPublishState((prev) => ({ ...prev, task: t }))
      messageApi.success(taskMode === 'rewrite' ? '发布版草稿已生成' : '发布成功')
      queryClient.invalidateQueries({ queryKey: ['articles'] })
    },
    onError: (t) => {
      setPublishState((prev) => ({ ...prev, task: t }))
      messageApi.error(`${taskMode === 'rewrite' ? '改写' : '发布'}失败：${t.error || '未知错误'}`)
    },
  })

  const startTask = async (slug: string, mode: 'publish' | 'rewrite') => {
    setPublishState({ taskId: null, slug, task: null })
    setTaskMode(mode)
    setModalOpen(true)
    try {
      const result = mode === 'publish'
        ? await publishArticle(slug)
        : await rewriteForPublish(slug, referenceBenchmarkId)
      setPublishState((prev) => ({ ...prev, taskId: result.task_id }))
    } catch (err) {
      messageApi.error(`启动任务失败：${(err as Error).message}`)
      setModalOpen(false)
    }
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

  const publishable = articles?.filter((article) => article.status !== 'published') ?? []
  const published = articles?.filter((article) => article.status === 'published') ?? []
  const busy = publishState.taskId !== null && task?.status !== 'completed' && task?.status !== 'failed'

  const columns = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      render: (title: string) => <Text style={{ fontSize: 13 }}>{title}</Text>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (status: string) => {
        const cfg = statusConfig[status] ?? { color: 'default', label: status }
        return <Tag color={cfg.color}>{cfg.label}</Tag>
      },
    },
    {
      title: '字数',
      dataIndex: 'word_count',
      key: 'word_count',
      width: 80,
      render: (value: number | null) => value ?? <Text type="secondary">-</Text>,
    },
    {
      title: '操作',
      key: 'action',
      width: 220,
      render: (_: unknown, record: Article) => (
        <div style={{ display: 'flex', gap: 6 }}>
          <Button size="small" onClick={() => startTask(record.slug, 'rewrite')}>
            发布前改写
          </Button>
          <Button type="primary" size="small" icon={<SendOutlined />} onClick={() => startTask(record.slug, 'publish')}>
            发布
          </Button>
        </div>
      ),
    },
  ]

  const publishedColumns = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      render: (title: string) => <Text style={{ fontSize: 13 }}>{title}</Text>,
    },
    {
      title: 'media_id',
      dataIndex: 'media_id',
      key: 'media_id',
      render: (value: string | null) => value ? (
        <Tooltip title={value}>
          <Text type="secondary" style={{ fontSize: 11, fontFamily: 'monospace' }}>
            {value.slice(0, 20)}...
          </Text>
        </Tooltip>
      ) : (
        <Text type="secondary">-</Text>
      ),
    },
    {
      title: '字数',
      dataIndex: 'word_count',
      key: 'word_count',
      width: 80,
      render: (value: number | null) => value ?? <Text type="secondary">-</Text>,
    },
  ]

  return (
    <>
      {contextHolder}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ background: '#fff', borderRadius: 8, boxShadow: '0 1px 4px rgba(0,0,0,0.08)', padding: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <ClockCircleOutlined style={{ color: '#faad14', fontSize: 16 }} />
            <Title level={5} style={{ margin: 0 }}>待发布 ({publishable.length})</Title>
          </div>
          <Select
            allowClear
            placeholder="可选：发布前改写使用的爆款参考"
            value={referenceBenchmarkId}
            onChange={setReferenceBenchmarkId}
            style={{ width: 420, maxWidth: '100%', marginBottom: 12 }}
            options={(referenceMaterials ?? []).filter((item) => item.id != null).map((item) => ({
              value: item.id as number,
              label: item.title,
            }))}
          />
          {publishable.length === 0 ? (
            <Empty description="没有待发布的文章" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <Table dataSource={publishable} columns={columns} rowKey="slug" size="small" pagination={{ pageSize: 10, size: 'small' }} />
          )}
        </div>

        <div style={{ background: '#fff', borderRadius: 8, boxShadow: '0 1px 4px rgba(0,0,0,0.08)', padding: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 16 }} />
            <Title level={5} style={{ margin: 0 }}>已发布 ({published.length})</Title>
          </div>
          {published.length === 0 ? (
            <Empty description="暂无已发布文章" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <Table dataSource={published} columns={publishedColumns} rowKey="slug" size="small" pagination={{ pageSize: 10, size: 'small' }} />
          )}
        </div>
      </div>

      <Modal
        title={`${taskMode === 'rewrite' ? '发布前改写' : '发布'}：${publishState.slug ?? ''}`}
        open={modalOpen}
        onCancel={() => !busy && setModalOpen(false)}
        footer={<Button type="primary" disabled={busy} onClick={() => setModalOpen(false)}>{busy ? '处理中...' : '关闭'}</Button>}
        width={560}
      >
        <Progress
          percent={task?.progress ?? 0}
          status={task?.status === 'failed' ? 'exception' : task?.status === 'completed' ? 'success' : 'active'}
          style={{ marginBottom: 12 }}
        />
        <div
          style={{
            maxHeight: 300,
            overflowY: 'auto',
            background: '#0d1117',
            borderRadius: 4,
            padding: '10px 12px',
            fontSize: 12,
            fontFamily: 'monospace',
            color: '#c9d1d9',
            lineHeight: 1.7,
          }}
        >
          {(task ? logs : []).filter(Boolean).map((line, index) => (
            <div key={index}>{line}</div>
          ))}
          {!publishState.taskId && <div style={{ color: '#888' }}>正在启动任务...</div>}
        </div>
        {task?.status === 'completed' && (
          <Alert
            type="success"
            style={{ marginTop: 12 }}
            title={taskMode === 'rewrite' ? `新草稿：${(task.result as Record<string, string> | null)?.slug ?? '-'}` : `发布成功：${(task.result as Record<string, string> | null)?.media_id ?? '-'}`}
            showIcon
          />
        )}
        {task?.status === 'failed' && (
          <Alert type="error" style={{ marginTop: 12 }} title={task.error ?? '任务失败'} showIcon />
        )}
      </Modal>
    </>
  )
}
