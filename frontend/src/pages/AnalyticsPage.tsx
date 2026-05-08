import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Card,
  Statistic,
  Table,
  Tag,
  Button,
  Tabs,
  Progress,
  Spin,
  Empty,
  Typography,
  message,
  Alert,
} from 'antd'
import {
  SyncOutlined,
  FileTextOutlined,
  ReadOutlined,
  ShareAltOutlined,
} from '@ant-design/icons'
import {
  getOverview,
  getArticlesAnalytics,
  fetchStats,
  getInsights,
} from '../api/analytics'
import type { ArticleAnalytics, InsightItem } from '../api/analytics'
import type { ColumnsType } from 'antd/es/table'

const { Text } = Typography

function formatDate(val: string | null): string {
  if (!val) return '—'
  return new Date(val).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function InsightsTable({ dimension }: { dimension: 'structure_type' | 'word_count_bucket' }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['insights', dimension],
    queryFn: () => getInsights(dimension),
  })

  if (isLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
        <Spin />
      </div>
    )
  }

  if (error) {
    return (
      <Alert
        type="error"
        title="加载失败"
        description={(error as Error).message}
        showIcon
      />
    )
  }

  if (!data || data.length === 0) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />
  }

  const maxReads = Math.max(...data.map((d) => d.avg_reads), 1)

  const columns: ColumnsType<InsightItem> = [
    {
      title: '标签',
      dataIndex: 'label',
      key: 'label',
      render: (label: string) => <Text style={{ fontSize: 13 }}>{label || '未分类'}</Text>,
    },
    {
      title: '篇数',
      dataIndex: 'count',
      key: 'count',
      width: 80,
      render: (count: number) => <Text style={{ fontSize: 13 }}>{count}</Text>,
    },
    {
      title: '平均阅读数',
      dataIndex: 'avg_reads',
      key: 'avg_reads',
      width: 280,
      render: (avg_reads: number) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Progress
            percent={Math.round((avg_reads / maxReads) * 100)}
            size="small"
            style={{ flex: 1, margin: 0 }}
            format={() => ''}
          />
          <Text style={{ fontSize: 13, minWidth: 40, textAlign: 'right' }}>
            {avg_reads.toFixed(0)}
          </Text>
        </div>
      ),
    },
  ]

  return (
    <Table<InsightItem>
      dataSource={data}
      columns={columns}
      rowKey="label"
      pagination={false}
      size="middle"
    />
  )
}

export default function AnalyticsPage() {
  const queryClient = useQueryClient()
  const [messageApi, contextHolder] = message.useMessage()
  const [activeTab, setActiveTab] = useState('structure_type')

  const { data: overview, isLoading: overviewLoading, error: overviewError } = useQuery({
    queryKey: ['analytics-overview'],
    queryFn: getOverview,
  })

  const { data: articles, isLoading: articlesLoading, error: articlesError } = useQuery({
    queryKey: ['analytics-articles'],
    queryFn: getArticlesAnalytics,
  })

  const fetchStatsMutation = useMutation({
    mutationFn: fetchStats,
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['analytics-overview'] })
      queryClient.invalidateQueries({ queryKey: ['analytics-articles'] })
      queryClient.invalidateQueries({ queryKey: ['insights'] })

      const parts = [
        `已同步 ${result.synced} 篇`,
        `API 获取 ${result.wechat_articles_found} 篇`,
        `更新 ${result.updated} 篇`,
      ]
      const errors = result.errors || []
      if (errors.length > 0) {
        messageApi.warning({
          content: `${parts.join('，')}（${errors.join('；')}）`,
          duration: 6,
          style: {
            marginLeft: 220,
            maxWidth: 'min(720px, calc(100vw - 268px))',
            whiteSpace: 'normal',
          },
        })
      } else {
        messageApi.success(parts.join('，'))
      }
    },
    onError: (error: Error) => {
      messageApi.error(`更新失败：${error.message}`)
    },
  })

  const sortedArticles = [...(articles ?? [])].sort(
    (a, b) => b.latest_read_count - a.latest_read_count
  )

  const articleColumns: ColumnsType<ArticleAnalytics> = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
      render: (title: string) => <Text style={{ fontSize: 13 }}>{title}</Text>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (status: string) =>
        status === 'published' ? (
          <Tag color="green" style={{ margin: 0 }}>已发布</Tag>
        ) : (
          <Tag style={{ margin: 0 }}>草稿</Tag>
        ),
    },
    {
      title: '结构类型',
      dataIndex: 'structure_type',
      key: 'structure_type',
      width: 120,
      render: (val: string | null) => (
        <Text type="secondary" style={{ fontSize: 12 }}>{val ?? '—'}</Text>
      ),
    },
    {
      title: '字数',
      dataIndex: 'word_count',
      key: 'word_count',
      width: 80,
      render: (val: number | null) => (
        <Text style={{ fontSize: 13 }}>{val ?? '—'}</Text>
      ),
    },
    {
      title: '阅读数',
      dataIndex: 'latest_read_count',
      key: 'latest_read_count',
      width: 90,
      render: (val: number) =>
        val === 0 ? (
          <Text type="secondary" style={{ fontSize: 12 }}>—</Text>
        ) : (
          <Text style={{ fontSize: 13 }}>{val}</Text>
        ),
    },
    {
      title: '分享数',
      dataIndex: 'latest_share_count',
      key: 'latest_share_count',
      width: 80,
      render: (val: number) =>
        val === 0 ? (
          <Text type="secondary" style={{ fontSize: 12 }}>—</Text>
        ) : (
          <Text style={{ fontSize: 13 }}>{val}</Text>
        ),
    },
    {
      title: '点赞数',
      dataIndex: 'latest_like_count',
      key: 'latest_like_count',
      width: 80,
      render: (val: number) =>
        val === 0 ? (
          <Text type="secondary" style={{ fontSize: 12 }}>—</Text>
        ) : (
          <Text style={{ fontSize: 13 }}>{val}</Text>
        ),
    },
    {
      title: '更新时间',
      dataIndex: 'stats_fetched_at',
      key: 'stats_fetched_at',
      width: 150,
      render: (val: string | null) => (
        <Text type="secondary" style={{ fontSize: 12 }}>{formatDate(val)}</Text>
      ),
    },
  ]

  if (overviewError) {
    return (
      <Alert
        type="error"
        title="加载失败"
        description={(overviewError as Error).message}
        showIcon
      />
    )
  }

  return (
    <>
      {contextHolder}

      {/* 第一区：总览卡片 */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          gap: 12,
          flexWrap: 'wrap',
          marginBottom: 16,
        }}
      >
        <Text strong style={{ fontSize: 15 }}>数据看板</Text>
        <Button
          type="primary"
          icon={<SyncOutlined spin={fetchStatsMutation.isPending} />}
          loading={fetchStatsMutation.isPending}
          onClick={() => fetchStatsMutation.mutate()}
        >
          更新数据
        </Button>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(112px, 1fr))',
          gap: 12,
          marginBottom: 20,
        }}
      >
        <Card size="small" loading={overviewLoading}>
          <Statistic
            title="总文章数"
            value={overview?.total_articles ?? 0}
            prefix={<FileTextOutlined />}
          />
        </Card>
        <Card size="small" loading={overviewLoading}>
          <Statistic
            title="已发布"
            value={overview?.published_articles ?? 0}
            styles={{ content: { color: '#52c41a' } }}
          />
        </Card>
        <Card size="small" loading={overviewLoading}>
          <Statistic
            title="草稿"
            value={overview?.draft_articles ?? 0}
            styles={{ content: { color: '#8c8c8c' } }}
          />
        </Card>
        <Card size="small" loading={overviewLoading}>
          <Statistic
            title="总阅读数"
            value={overview?.total_reads ?? 0}
            prefix={<ReadOutlined />}
          />
        </Card>
        <Card size="small" loading={overviewLoading}>
          <Statistic
            title="总分享数"
            value={overview?.total_shares ?? 0}
            prefix={<ShareAltOutlined />}
          />
        </Card>
        <Card size="small" loading={overviewLoading}>
          <Statistic
            title="篇均阅读"
            value={overview?.avg_read_per_article ?? 0}
            precision={1}
          />
        </Card>
      </div>

      {/* 第二区：文章绩效表格 */}
      <div
        style={{
          background: '#fff',
          borderRadius: 8,
          boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
          padding: 16,
          marginBottom: 20,
        }}
      >
        <Text strong style={{ fontSize: 15, display: 'block', marginBottom: 14 }}>
          文章绩效
        </Text>

        {articlesError ? (
          <Alert
            type="error"
            title="加载失败"
            description={(articlesError as Error).message}
            showIcon
          />
        ) : (
          <Table<ArticleAnalytics>
            dataSource={sortedArticles}
            columns={articleColumns}
            rowKey={(record) =>
              record.id != null ? String(record.id) : record.slug ?? record.title ?? ''
            }
            loading={articlesLoading}
            pagination={{ pageSize: 20, showSizeChanger: false }}
            scroll={{ x: 760 }}
            size="middle"
            locale={{
              emptyText: (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="暂无文章数据"
                />
              ),
            }}
          />
        )}
      </div>

      {/* 第三区：关联分析 */}
      <div
        style={{
          background: '#fff',
          borderRadius: 8,
          boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
          padding: 16,
        }}
      >
        <Text strong style={{ fontSize: 15, display: 'block', marginBottom: 14 }}>
          关联分析
        </Text>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'structure_type',
              label: '按结构类型',
              children: <InsightsTable dimension="structure_type" />,
            },
            {
              key: 'word_count_bucket',
              label: '按字数分桶',
              children: <InsightsTable dimension="word_count_bucket" />,
            },
          ]}
        />
      </div>
    </>
  )
}
