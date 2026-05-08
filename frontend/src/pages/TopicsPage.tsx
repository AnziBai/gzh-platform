import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Button, Tag, Spin, Alert, Empty, Typography, Table, Progress,
  Tabs, message,
} from 'antd'
import { FireOutlined, CheckOutlined, StopOutlined } from '@ant-design/icons'
import { getTopics, scrapeTopics, selectTopic, dismissTopic } from '../api/topics'
import { useTaskStream } from '../hooks/useTaskStream'
import type { Topic } from '../api/topics'

const { Title, Text } = Typography

const statusConfig: Record<string, { color: string; label: string }> = {
  new:       { color: 'processing', label: '待处理' },
  selected:  { color: 'success',    label: '已选'   },
  used:      { color: 'default',    label: '已使用' },
  dismissed: { color: 'error',      label: '已忽略' },
}

const platformConfig: Record<string, { color: string; label: string }> = {
  toutiao:   { color: 'red',     label: '头条' },
  sina:      { color: 'orange',  label: '新浪财经' },
  eastmoney: { color: 'blue',    label: '东方财富' },
  xueqiu:    { color: 'green',   label: '雪球' },
}

const TAB_STATUS: Record<string, string | undefined> = {
  all:       undefined,
  new:       'new',
  selected:  'selected',
  dismissed: 'dismissed',
}

export default function TopicsPage() {
  const queryClient = useQueryClient()
  const [messageApi, contextHolder] = message.useMessage()
  const [activeTab, setActiveTab] = useState('all')
  const [taskId, setTaskId] = useState<string | null>(null)
  const [scraping, setScraping] = useState(false)
  const [actionLoading, setActionLoading] = useState<number | null>(null)

  const filterStatus = TAB_STATUS[activeTab]

  const { data: topics, isLoading, error } = useQuery({
    queryKey: ['topics', filterStatus],
    queryFn: () => getTopics(filterStatus),
  })

  const { task, logs } = useTaskStream({
    taskId,
    onComplete: () => {
      setScraping(false)
      messageApi.success('热点抓取完成！')
      queryClient.invalidateQueries({ queryKey: ['topics'] })
    },
    onError: (t) => {
      setScraping(false)
      messageApi.error(`抓取失败：${t.error || '未知错误'}`)
    },
  })

  const handleScrape = async (platform: string = 'all') => {
    setScraping(true)
    setTaskId(null)
    try {
      const { task_id } = await scrapeTopics(platform)
      setTaskId(task_id)
    } catch {
      setScraping(false)
      messageApi.error('启动抓取任务失败')
    }
  }

  const handleSelect = async (id: number) => {
    setActionLoading(id)
    try {
      await selectTopic(id)
      messageApi.success('已选为选题')
      queryClient.invalidateQueries({ queryKey: ['topics'] })
    } catch {
      messageApi.error('操作失败')
    } finally {
      setActionLoading(null)
    }
  }

  const handleDismiss = async (id: number) => {
    setActionLoading(id)
    try {
      await dismissTopic(id)
      messageApi.success('已忽略')
      queryClient.invalidateQueries({ queryKey: ['topics'] })
    } catch {
      messageApi.error('操作失败')
    } finally {
      setActionLoading(null)
    }
  }

  const columns = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      render: (title: string, record: Topic) =>
        record.source_url ? (
          <a href={record.source_url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 13, color: '#1a1a1a' }}>
            {title}
          </a>
        ) : (
          <Text style={{ fontSize: 13 }}>{title}</Text>
        ),
    },
    {
      title: '平台',
      dataIndex: 'platform',
      key: 'platform',
      width: 100,
      render: (platform: string) => {
        const cfg = platformConfig[platform] ?? { color: 'default', label: platform }
        return <Tag color={cfg.color} style={{ margin: 0, fontSize: 11 }}>{cfg.label}</Tag>
      },
    },
    {
      title: '热度值',
      dataIndex: 'hot_value',
      key: 'hot_value',
      width: 100,
      render: (v: number | null) =>
        v != null ? (
          <Text style={{ fontSize: 13, color: '#fa8c16', fontWeight: 500 }}>
            {v.toLocaleString()}
          </Text>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
    {
      title: '相关度',
      dataIndex: 'relevance_score',
      key: 'relevance_score',
      width: 130,
      render: (v: number | null, record: Topic) => {
        if (v == null) return <Text type="secondary">—</Text>
        const pct = Math.round(v * 100)
        return (
          <div title={record.relevance_reason ?? undefined}>
            <Progress
              percent={pct}
              size="small"
              strokeColor={pct >= 70 ? '#52c41a' : pct >= 40 ? '#faad14' : '#ff4d4f'}
              format={(p) => <span style={{ fontSize: 11 }}>{p}%</span>}
            />
          </div>
        )
      },
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
      title: '操作',
      key: 'action',
      width: 140,
      render: (_: unknown, record: Topic) => {
        const busy = actionLoading === record.id
        if (record.status === 'selected' || record.status === 'used') {
          return <Text type="secondary" style={{ fontSize: 12 }}>—</Text>
        }
        return (
          <div style={{ display: 'flex', gap: 6 }}>
            {record.status !== 'dismissed' && (
              <Button
                type="primary"
                size="small"
                icon={<CheckOutlined />}
                loading={busy}
                onClick={() => handleSelect(record.id)}
              >
                选为选题
              </Button>
            )}
            {record.status !== 'dismissed' && (
              <Button
                size="small"
                danger
                icon={<StopOutlined />}
                loading={busy}
                onClick={() => handleDismiss(record.id)}
              >
                忽略
              </Button>
            )}
          </div>
        )
      },
    },
  ]

  const tabItems = [
    { key: 'all',       label: '全部' },
    { key: 'new',       label: '待处理' },
    { key: 'selected',  label: '已选' },
    { key: 'dismissed', label: '已忽略' },
  ]

  const isStreaming = scraping && taskId !== null && task?.status !== 'completed' && task?.status !== 'failed'

  if (error) {
    return <Alert type="error" message="加载失败" description={(error as Error).message} showIcon />
  }

  return (
    <>
      {contextHolder}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* 顶部操作卡片 */}
        <div
          style={{
            background: '#fff',
            borderRadius: 8,
            boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
            padding: 20,
            display: 'flex',
            alignItems: 'center',
            gap: 16,
            flexWrap: 'wrap',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <FireOutlined style={{ color: '#fa8c16', fontSize: 18 }} />
            <Title level={5} style={{ margin: 0 }}>金融热点选题</Title>
          </div>

          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Button
              type="primary"
              icon={<FireOutlined />}
              loading={scraping}
              onClick={() => handleScrape('all')}
            >
              {scraping ? '抓取中…' : '全部平台抓取'}
            </Button>
            <Button
              loading={scraping}
              onClick={() => handleScrape('toutiao')}
            >
              头条热榜
            </Button>
            <Button
              loading={scraping}
              onClick={() => handleScrape('sina')}
            >
              新浪财经
            </Button>
            <Button
              loading={scraping}
              onClick={() => handleScrape('eastmoney')}
            >
              东方财富
            </Button>
            <Button
              loading={scraping}
              onClick={() => handleScrape('xueqiu')}
            >
              雪球
            </Button>
          </div>

          {/* 进度条 + 日志 */}
          {taskId && (
            <div style={{ flex: 1, minWidth: 280 }}>
              <Progress
                percent={task?.progress ?? 0}
                size="small"
                status={
                  task?.status === 'failed' ? 'exception'
                  : task?.status === 'completed' ? 'success'
                  : 'active'
                }
                style={{ marginBottom: isStreaming || logs.length > 0 ? 6 : 0 }}
              />
              {(isStreaming || logs.length > 0) && (
                <div
                  style={{
                    maxHeight: 80,
                    overflowY: 'auto',
                    background: '#0d1117',
                    borderRadius: 4,
                    padding: '6px 10px',
                    fontSize: 11,
                    fontFamily: 'monospace',
                    color: '#c9d1d9',
                    lineHeight: 1.6,
                  }}
                >
                  {logs.filter(Boolean).map((line, i) => (
                    <div key={i}>{line}</div>
                  ))}
                  {!taskId && <div style={{ color: '#888' }}>正在启动任务…</div>}
                </div>
              )}
            </div>
          )}
        </div>

        {/* 选题列表卡片 */}
        <div
          style={{
            background: '#fff',
            borderRadius: 8,
            boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
            padding: 24,
          }}
        >
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            items={tabItems}
            style={{ marginBottom: 0 }}
          />

          {isLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 60 }}>
              <Spin size="large" />
            </div>
          ) : !topics || topics.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={
                activeTab === 'all'
                  ? '点击上方按钮抓取金融热点（头条/新浪财经/东方财富/雪球）'
                  : `暂无${tabItems.find((t) => t.key === activeTab)?.label ?? ''}内容`
              }
              style={{ padding: '48px 0' }}
            />
          ) : (
            <Table
              dataSource={topics}
              columns={columns}
              rowKey="id"
              size="small"
              pagination={{ pageSize: 20, size: 'small' }}
            />
          )}
        </div>
      </div>
    </>
  )
}
