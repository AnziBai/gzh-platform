import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Input, Select, Tag, Spin, Alert, Empty, Typography, Progress, Popconfirm, message } from 'antd'
import { PlusOutlined, ThunderboltOutlined, DeleteOutlined } from '@ant-design/icons'
import Markdown from 'react-markdown'
import { getArticles, getArticleBySlug, generateArticle, deleteArticle, getHotReferenceArticles } from '../api/articles'
import { useTaskStream } from '../hooks/useTaskStream'
import type { Article } from '../api/articles'

const { Title, Text } = Typography

const statusConfig: Record<string, { color: string; label: string }> = {
  draft: { color: 'default', label: '草稿' },
  published: { color: 'success', label: '已发布' },
  untracked: { color: 'warning', label: '未导入' },
}

export default function WorkshopPage() {
  const queryClient = useQueryClient()
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null)
  const [topic, setTopic] = useState('')
  const [referenceSlug, setReferenceSlug] = useState<string | undefined>()
  const [taskId, setTaskId] = useState<string | null>(null)
  const [generating, setGenerating] = useState(false)
  const logsEndRef = useRef<HTMLDivElement>(null)
  const [messageApi, contextHolder] = message.useMessage()

  const { data: articles, isLoading, error } = useQuery({
    queryKey: ['articles'],
    queryFn: getArticles,
  })

  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ['article', selectedSlug],
    queryFn: () => getArticleBySlug(selectedSlug!),
    enabled: !!selectedSlug,
  })

  const { data: hotReferences } = useQuery({
    queryKey: ['hot-reference-articles'],
    queryFn: getHotReferenceArticles,
  })

  const { task, logs } = useTaskStream({
    taskId,
    onComplete: () => {
      setGenerating(false)
      messageApi.success('文章生成完成！')
      queryClient.invalidateQueries({ queryKey: ['articles'] })
    },
    onError: (t) => {
      setGenerating(false)
      messageApi.error(`生成失败：${t.error || '未知错误'}`)
    },
  })

  // Auto-scroll logs
  const scrollLogs = () => {
    setTimeout(() => logsEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 50)
  }

  const handleGenerate = async () => {
    if (!topic.trim()) {
      messageApi.warning('请输入文章主题')
      return
    }
    setGenerating(true)
    setTaskId(null)
    try {
      const { task_id } = await generateArticle(topic.trim(), undefined, referenceSlug)
      setTaskId(task_id)
      scrollLogs()
    } catch (e) {
      setGenerating(false)
      messageApi.error('启动生成任务失败')
    }
  }

  const handleDelete = async (id: number, e?: React.MouseEvent) => {
    e?.stopPropagation()
    try {
      await deleteArticle(id)
      messageApi.success('已删除')
      if (selected && selected.id === id) setSelectedSlug(null)
      queryClient.invalidateQueries({ queryKey: ['articles'] })
    } catch (err) {
      messageApi.error(`删除失败：${(err as Error).message}`)
    }
  }

  const selected: Article | null = detail ?? null

  if (isLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 80 }}>
        <Spin size="large" />
      </div>
    )
  }

  if (error) {
    return (
      <Alert type="error" title="加载失败" description={(error as Error).message} showIcon />
    )
  }

  return (
    <>
      {contextHolder}
      <div style={{ display: 'flex', gap: 16, height: 'calc(100vh - 48px)' }}>
        {/* 左侧：文章列表 + 生成面板 */}
        <div
          style={{
            width: 300,
            flexShrink: 0,
            display: 'flex',
            flexDirection: 'column',
            gap: 12,
          }}
        >
          {/* 生成卡片 */}
          <div
            style={{
              background: '#fff',
              borderRadius: 8,
              boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
              padding: 16,
            }}
          >
            <Text strong style={{ fontSize: 14, display: 'block', marginBottom: 10 }}>
              一键生成新文章
            </Text>
            <Input.TextArea
              placeholder="输入文章主题，例如：概率思维在投资中的应用"
              rows={3}
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              disabled={generating}
              style={{ marginBottom: 8, fontSize: 13 }}
            />
            <Select
              allowClear
              placeholder="可选：仿写一篇爆款文章"
              value={referenceSlug}
              onChange={setReferenceSlug}
              disabled={generating}
              style={{ width: '100%', marginBottom: 8 }}
              options={(hotReferences ?? []).map((article) => ({
                value: article.slug,
                label: `${article.title}（${article.read_count}阅读）`,
              }))}
            />
            <Button
              type="primary"
              icon={<ThunderboltOutlined />}
              block
              loading={generating}
              onClick={handleGenerate}
            >
              {generating ? '生成中…' : '生成文章'}
            </Button>

            {/* 进度 + 日志 */}
            {taskId && (
              <div style={{ marginTop: 12 }}>
                <Progress
                  percent={task?.progress ?? 0}
                  size="small"
                  status={task?.status === 'failed' ? 'exception' : task?.status === 'completed' ? 'success' : 'active'}
                />
                <div
                  style={{
                    marginTop: 8,
                    maxHeight: 160,
                    overflowY: 'auto',
                    background: '#0d1117',
                    borderRadius: 4,
                    padding: '8px 10px',
                    fontSize: 11,
                    fontFamily: 'monospace',
                    color: '#c9d1d9',
                    lineHeight: 1.6,
                  }}
                  onClick={scrollLogs}
                >
                  {logs.filter(Boolean).map((line, i) => (
                    <div key={i}>{line}</div>
                  ))}
                  <div ref={logsEndRef} />
                </div>
              </div>
            )}
          </div>

          {/* 文章列表 */}
          <div
            style={{
              flex: 1,
              background: '#fff',
              borderRadius: 8,
              boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                padding: '12px 16px 10px',
                borderBottom: '1px solid #f0f0f0',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <Text strong style={{ fontSize: 14 }}>
                文章列表 {articles ? `(${articles.length})` : ''}
              </Text>
              <Button type="text" size="small" icon={<PlusOutlined />} disabled>
                导入
              </Button>
            </div>

            <div style={{ overflowY: 'auto', flex: 1 }}>
              {!articles || articles.length === 0 ? (
                <Empty description="暂无文章" style={{ marginTop: 40 }} image={Empty.PRESENTED_IMAGE_SIMPLE} />
              ) : (
                articles.map((article) => {
                  const cfg = statusConfig[article.status] ?? { color: 'default', label: article.status }
                  const isActive = article.slug === selectedSlug
                  return (
                    <div
                      key={article.slug}
                      onClick={() => setSelectedSlug(article.slug)}
                      style={{
                        padding: '10px 16px',
                        cursor: 'pointer',
                        borderBottom: '1px solid #f5f5f5',
                        background: isActive ? '#e6f4ff' : 'transparent',
                        transition: 'background 0.15s',
                      }}
                    >
                      <div
                        style={{
                          fontSize: 13,
                          fontWeight: isActive ? 600 : 400,
                          color: '#1a1a1a',
                          marginBottom: 5,
                          lineHeight: 1.4,
                          display: '-webkit-box',
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: 'vertical',
                          overflow: 'hidden',
                        }}
                      >
                        {article.title}
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <Tag color={cfg.color} style={{ margin: 0, fontSize: 11 }}>
                          {cfg.label}
                        </Tag>
                        {article.word_count != null && (
                          <Text type="secondary" style={{ fontSize: 11 }}>
                            {article.word_count} 字
                          </Text>
                        )}
                        {!article.media_id && article.status !== 'published' && article.id != null && (
                          <Popconfirm
                            title="确认删除该文章？"
                            okText="删除"
                            cancelText="取消"
                            okButtonProps={{ danger: true }}
                            onConfirm={(e) => handleDelete(article.id!, e)}
                          >
                            <Button
                              type="text"
                              danger
                              icon={<DeleteOutlined />}
                              size="small"
                              style={{ marginLeft: 'auto', padding: '0 4px' }}
                              onClick={(e) => e.stopPropagation()}
                            />
                          </Popconfirm>
                        )}
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          </div>
        </div>

        {/* 右侧：文章详情 */}
        <div
          style={{
            flex: 1,
            background: '#fff',
            borderRadius: 8,
            boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
            overflow: 'auto',
            padding: 32,
          }}
        >
          {!selectedSlug ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
              <Empty description="点击左侧文章查看详情" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            </div>
          ) : detailLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 80 }}>
              <Spin size="large" />
            </div>
          ) : !selected ? (
            <Alert type="error" title="文章加载失败" showIcon />
          ) : (
            <>
              <Title level={3} style={{ marginTop: 0, marginBottom: 16 }}>
                {selected.title}
              </Title>

              <div
                style={{
                  display: 'flex',
                  gap: 24,
                  marginBottom: 24,
                  padding: '12px 16px',
                  background: '#fafafa',
                  borderRadius: 6,
                  flexWrap: 'wrap',
                }}
              >
                <div>
                  <Text type="secondary" style={{ fontSize: 12 }}>状态</Text>
                  <div style={{ marginTop: 4 }}>
                    <Tag color={(statusConfig[selected.status] ?? statusConfig.untracked).color}>
                      {(statusConfig[selected.status] ?? statusConfig.untracked).label}
                    </Tag>
                  </div>
                </div>
                {selected.word_count != null && (
                  <div>
                    <Text type="secondary" style={{ fontSize: 12 }}>字数</Text>
                    <div style={{ marginTop: 4, fontSize: 14, fontWeight: 500 }}>{selected.word_count}</div>
                  </div>
                )}
                {selected.image_count != null && (
                  <div>
                    <Text type="secondary" style={{ fontSize: 12 }}>图片数</Text>
                    <div style={{ marginTop: 4, fontSize: 14, fontWeight: 500 }}>{selected.image_count}</div>
                  </div>
                )}
                {selected.media_id && (
                  <div>
                    <Text type="secondary" style={{ fontSize: 12 }}>media_id</Text>
                    <div style={{ marginTop: 4, fontSize: 12, fontFamily: 'monospace', color: '#666' }}>{selected.media_id}</div>
                  </div>
                )}
              </div>

              {selected.content ? (
                <div style={{ lineHeight: 1.8, fontSize: 15, color: '#333' }}>
                  <Markdown>{selected.content}</Markdown>
                </div>
              ) : (
                <Empty description="暂无内容" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              )}
            </>
          )}
        </div>
      </div>
    </>
  )
}
