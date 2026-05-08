import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Button, Tag, Spin, Alert, Empty, Typography, Table, Progress,
  Modal, message, Tooltip,
} from 'antd'
import { SendOutlined, CheckCircleOutlined, ClockCircleOutlined } from '@ant-design/icons'
import { getArticles, publishArticle } from '../api/articles'
import { useTaskStream } from '../hooks/useTaskStream'
import type { Article, Task } from '../api/articles'

const { Title, Text } = Typography

interface PublishState {
  taskId: string | null
  slug: string | null
  logs: string[]
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
  const [publishState, setPublishState] = useState<PublishState>({
    taskId: null,
    slug: null,
    logs: [],
    task: null,
  })
  const [modalOpen, setModalOpen] = useState(false)

  const { data: articles, isLoading, error } = useQuery({
    queryKey: ['articles'],
    queryFn: getArticles,
  })

  // SSE stream for current publish task
  const { task, logs } = useTaskStream({
    taskId: publishState.taskId,
    onComplete: (t) => {
      setPublishState((prev) => ({ ...prev, task: t, logs: logs }))
      messageApi.success('发布成功！')
      queryClient.invalidateQueries({ queryKey: ['articles'] })
    },
    onError: (t) => {
      setPublishState((prev) => ({ ...prev, task: t, logs: logs }))
      messageApi.error(`发布失败：${t.error || '未知错误'}`)
    },
  })

  const handlePublish = async (slug: string) => {
    setPublishState({ taskId: null, slug, logs: [], task: null })
    setModalOpen(true)
    try {
      const { task_id } = await publishArticle(slug)
      setPublishState((prev) => ({ ...prev, taskId: task_id }))
    } catch {
      messageApi.error('启动发布任务失败')
      setModalOpen(false)
    }
  }

  // Articles eligible for publishing (draft or untracked, not yet published)
  const publishable = articles?.filter((a) => a.status !== 'published') ?? []
  const published = articles?.filter((a) => a.status === 'published') ?? []

  const columns = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      render: (title: string) => (
        <Text style={{ fontSize: 13 }}>{title}</Text>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (status: string) => {
        const cfg = statusConfig[status] ?? { color: 'default', label: status }
        return <Tag color={cfg.color} style={{ fontSize: 11 }}>{cfg.label}</Tag>
      },
    },
    {
      title: '字数',
      dataIndex: 'word_count',
      key: 'word_count',
      width: 70,
      render: (v: number | null) => v != null ? <Text type="secondary" style={{ fontSize: 12 }}>{v}</Text> : '—',
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_: unknown, record: Article) => (
        <Button
          type="primary"
          size="small"
          icon={<SendOutlined />}
          onClick={() => handlePublish(record.slug)}
        >
          发布
        </Button>
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
      render: (v: string | null) =>
        v ? (
          <Tooltip title={v}>
            <Text type="secondary" style={{ fontSize: 11, fontFamily: 'monospace' }}>
              {v.slice(0, 20)}…
            </Text>
          </Tooltip>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
    {
      title: '字数',
      dataIndex: 'word_count',
      key: 'word_count',
      width: 70,
      render: (v: number | null) => v != null ? <Text type="secondary" style={{ fontSize: 12 }}>{v}</Text> : '—',
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
    return <Alert type="error" message="加载失败" description={(error as Error).message} showIcon />
  }

  const isPublishing = publishState.taskId !== null && task?.status !== 'completed' && task?.status !== 'failed'

  return (
    <>
      {contextHolder}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* 待发布 */}
        <div style={{ background: '#fff', borderRadius: 8, boxShadow: '0 1px 4px rgba(0,0,0,0.08)', padding: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <ClockCircleOutlined style={{ color: '#faad14', fontSize: 16 }} />
            <Title level={5} style={{ margin: 0 }}>待发布 ({publishable.length})</Title>
          </div>
          {publishable.length === 0 ? (
            <Empty description="没有待发布的文章" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <Table
              dataSource={publishable}
              columns={columns}
              rowKey="slug"
              size="small"
              pagination={{ pageSize: 10, size: 'small' }}
            />
          )}
        </div>

        {/* 已发布 */}
        <div style={{ background: '#fff', borderRadius: 8, boxShadow: '0 1px 4px rgba(0,0,0,0.08)', padding: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 16 }} />
            <Title level={5} style={{ margin: 0 }}>已发布 ({published.length})</Title>
          </div>
          {published.length === 0 ? (
            <Empty description="暂无已发布文章" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <Table
              dataSource={published}
              columns={publishedColumns}
              rowKey="slug"
              size="small"
              pagination={{ pageSize: 10, size: 'small' }}
            />
          )}
        </div>
      </div>

      {/* 发布进度弹窗 */}
      <Modal
        title={`发布：${publishState.slug}`}
        open={modalOpen}
        onCancel={() => !isPublishing && setModalOpen(false)}
        footer={
          <Button
            type="primary"
            disabled={isPublishing}
            onClick={() => setModalOpen(false)}
          >
            {isPublishing ? '发布中…' : '关闭'}
          </Button>
        }
        width={560}
      >
        <Progress
          percent={task?.progress ?? 0}
          status={
            task?.status === 'failed' ? 'exception'
            : task?.status === 'completed' ? 'success'
            : 'active'
          }
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
          {(task ? logs : []).filter(Boolean).map((line, i) => (
            <div key={i}>{line}</div>
          ))}
          {!publishState.taskId && <div style={{ color: '#888' }}>正在启动任务…</div>}
        </div>
        {task?.status === 'completed' && task.result && (
          <Alert
            type="success"
            style={{ marginTop: 12 }}
            message={`发布成功！media_id: ${(task.result as Record<string, string>).media_id ?? '—'}`}
            showIcon
          />
        )}
        {task?.status === 'failed' && (
          <Alert type="error" style={{ marginTop: 12 }} message={task.error ?? '发布失败'} showIcon />
        )}
      </Modal>
    </>
  )
}
