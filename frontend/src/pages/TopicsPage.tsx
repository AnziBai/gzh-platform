import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Button, Tag, Spin, Alert, Empty, Typography, Table, Progress, Input,
  Tabs, message, Modal, Select, List, Divider,
} from 'antd'
import { FireOutlined, CheckOutlined, StopOutlined, FileTextOutlined } from '@ant-design/icons'
import { getTopics, scrapeTopics, selectTopic, dismissTopic, generateTopicArticle, generateTopicBrief } from '../api/topics'
import { getBenchmarks } from '../api/benchmarks'
import { getHotReferenceArticles } from '../api/articles'
import { getKnowledgeFiles, recommendKnowledge } from '../api/knowledge'
import { useTaskStream } from '../hooks/useTaskStream'
import type { Topic } from '../api/topics'
import type { KnowledgeChunk } from '../api/knowledge'

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
  aihot:     { color: 'purple',  label: 'AI HOT' },
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
  const [workflowTaskId, setWorkflowTaskId] = useState<string | null>(null)
  const [workflowMode, setWorkflowMode] = useState<'brief' | 'article' | null>(null)
  const [scraping, setScraping] = useState(false)
  const [actionLoading, setActionLoading] = useState<number | null>(null)
  const [briefTopic, setBriefTopic] = useState<Topic | null>(null)
  const [selectedMaterialIds, setSelectedMaterialIds] = useState<number[]>([])
  const [selectedReferenceSlug, setSelectedReferenceSlug] = useState<string | null>(null)
  const [selectedKnowledgeFileIds, setSelectedKnowledgeFileIds] = useState<number[]>([])
  const [selectedKnowledgeChunkIds, setSelectedKnowledgeChunkIds] = useState<number[]>([])
  const [recommendedKnowledgeChunks, setRecommendedKnowledgeChunks] = useState<KnowledgeChunk[]>([])
  const [knowledgeRecommending, setKnowledgeRecommending] = useState(false)
  const [knowledgeSelectionTouched, setKnowledgeSelectionTouched] = useState(false)
  const [sourceGroup, setSourceGroup] = useState<'finance' | 'aihot' | 'all'>('finance')
  const [scrapeMode, setScrapeMode] = useState<'selected' | 'all'>('selected')
  const [sinceHours, setSinceHours] = useState(24)
  const [category, setCategory] = useState<string | undefined>()
  const [keyword, setKeyword] = useState('')

  const filterStatus = TAB_STATUS[activeTab]

  const { data: topics, isLoading, error } = useQuery({
    queryKey: ['topics', filterStatus],
    queryFn: () => getTopics(filterStatus),
  })

  const { data: factMaterials } = useQuery({
    queryKey: ['benchmarks', 'fact_material'],
    queryFn: () => getBenchmarks('fact_material'),
  })

  const { data: hotReferences } = useQuery({
    queryKey: ['hot-reference-articles'],
    queryFn: getHotReferenceArticles,
  })

  const { data: knowledgeFiles } = useQuery({
    queryKey: ['knowledge-files'],
    queryFn: getKnowledgeFiles,
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

  const { task: workflowTask, logs: workflowLogs } = useTaskStream({
    taskId: workflowTaskId,
    onComplete: () => {
      messageApi.success(workflowMode === 'brief' ? '创作简报已生成' : '文章已生成')
      setWorkflowMode(null)
      queryClient.invalidateQueries({ queryKey: ['topics'] })
      queryClient.invalidateQueries({ queryKey: ['articles'] })
      if (briefTopic) {
        getTopics().then((items) => {
          const fresh = items.find((item) => item.id === briefTopic.id)
          if (fresh) setBriefTopic(fresh)
        })
      }
    },
    onError: (t) => {
      messageApi.error(t.error || '任务失败')
      setWorkflowMode(null)
    },
  })

  const handleScrape = async (platform: string = 'all') => {
    setScraping(true)
    setTaskId(null)
    try {
      const { task_id } = await scrapeTopics({
        platform,
        source_group: sourceGroup,
        mode: scrapeMode,
        category,
        since_hours: sinceHours,
        keyword: keyword.trim() || undefined,
      })
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

  const openBriefModal = async (topic: Topic) => {
    const existingKnowledgeChunkIds = topic.knowledge_chunk_ids ?? []
    setBriefTopic(topic)
    setSelectedMaterialIds(topic.material_ids ?? [])
    setSelectedReferenceSlug(topic.reference_article_slug ?? null)
    setSelectedKnowledgeFileIds([])
    setSelectedKnowledgeChunkIds(existingKnowledgeChunkIds)
    setRecommendedKnowledgeChunks([])
    setKnowledgeSelectionTouched(false)

    setKnowledgeRecommending(true)
    try {
      const recommendation = await recommendKnowledge({ topic: topic.title, hotspot_title: topic.title })
      const chunks = recommendation.knowledge_chunks ?? []
      setRecommendedKnowledgeChunks(chunks)
      if (existingKnowledgeChunkIds.length === 0) {
        setSelectedKnowledgeChunkIds(chunks.slice(0, 5).map((chunk) => chunk.id))
      }
    } catch {
      setRecommendedKnowledgeChunks([])
    } finally {
      setKnowledgeRecommending(false)
    }
  }

  const handleKnowledgeFileChange = async (fileIds: number[]) => {
    setSelectedKnowledgeFileIds(fileIds)
    if (!briefTopic) return

    setKnowledgeRecommending(true)
    try {
      const recommendation = await recommendKnowledge({
        topic: briefTopic.title,
        hotspot_title: briefTopic.title,
        knowledge_file_ids: fileIds.length > 0 ? fileIds : undefined,
      })
      const chunks = recommendation.knowledge_chunks ?? []
      setRecommendedKnowledgeChunks(chunks)
      if (!knowledgeSelectionTouched) {
        setSelectedKnowledgeChunkIds(chunks.slice(0, 5).map((chunk) => chunk.id))
      }
    } catch {
      setRecommendedKnowledgeChunks([])
      if (!knowledgeSelectionTouched) {
        setSelectedKnowledgeChunkIds([])
      }
    } finally {
      setKnowledgeRecommending(false)
    }
  }

  const handleGenerateBrief = async () => {
    if (!briefTopic) return
    setWorkflowMode('brief')
    try {
      const { task_id } = await generateTopicBrief(briefTopic.id, {
        material_ids: selectedMaterialIds,
        reference_article_slug: selectedReferenceSlug,
        knowledge_chunk_ids: selectedKnowledgeChunkIds,
      })
      setWorkflowTaskId(task_id)
    } catch {
      setWorkflowMode(null)
      messageApi.error('启动简报任务失败')
    }
  }

  const handleGenerateArticle = async () => {
    if (!briefTopic) return
    setWorkflowMode('article')
    try {
      const { task_id } = await generateTopicArticle(briefTopic.id)
      setWorkflowTaskId(task_id)
    } catch {
      setWorkflowMode(null)
      messageApi.error('启动文章生成任务失败')
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
        return (
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {record.status !== 'dismissed' && (
              <Button
                size="small"
                icon={<FileTextOutlined />}
                loading={busy}
                onClick={() => openBriefModal(record)}
              >
                创作简报
              </Button>
            )}
            {record.status !== 'dismissed' && (
              <Button
                type="primary"
                size="small"
                icon={<CheckOutlined />}
                loading={busy}
                onClick={() => handleSelect(record.id)}
                disabled={record.status === 'selected' || record.status === 'used'}
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

  const readyKnowledgeFiles = (knowledgeFiles ?? []).filter((file) => file.status === 'ready')
  const selectedMissingKnowledgeChunkOptions = selectedKnowledgeChunkIds
    .filter((id) => !recommendedKnowledgeChunks.some((chunk) => chunk.id === id))
    .map((id) => ({
      value: id,
      label: `Knowledge #${id}`,
    }))
  const knowledgeChunkOptions = [
    ...recommendedKnowledgeChunks.map((chunk) => {
      const title = chunk.title || chunk.content.slice(0, 48)
      return {
        value: chunk.id,
        label: chunk.reason ? `${title} - ${chunk.reason}` : title,
      }
    }),
    ...selectedMissingKnowledgeChunkOptions,
  ]

  const isStreaming = scraping && taskId !== null && task?.status !== 'completed' && task?.status !== 'failed'

  if (error) {
    return <Alert type="error" title="加载失败" description={(error as Error).message} showIcon />
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

          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
            <Select
              value={sourceGroup}
              style={{ width: 140 }}
              onChange={setSourceGroup}
              options={[
                { value: 'finance', label: '财经热点' },
                { value: 'aihot', label: 'AI 热点' },
                { value: 'all', label: '全部来源' },
              ]}
            />
            <Select
              value={scrapeMode}
              style={{ width: 120 }}
              onChange={setScrapeMode}
              options={[
                { value: 'selected', label: '精选' },
                { value: 'all', label: '全部' },
              ]}
            />
            <Select
              value={sinceHours}
              style={{ width: 140 }}
              onChange={setSinceHours}
              options={[
                { value: 6, label: '最近 6 小时' },
                { value: 24, label: '最近 24 小时' },
                { value: 72, label: '最近 3 天' },
              ]}
            />
            <Select
              allowClear
              placeholder="分类"
              style={{ width: 140 }}
              value={category}
              onChange={setCategory}
              options={[
                { value: 'ai', label: 'AI' },
                { value: 'finance', label: '财经' },
                { value: 'tech', label: '科技' },
                { value: 'business', label: '商业' },
              ]}
            />
            <Input.Search
              allowClear
              placeholder="关键词"
              style={{ width: 180 }}
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              onSearch={() => handleScrape('all')}
              disabled={scraping}
            />
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

      <Modal
        title="热点创作简报"
        open={!!briefTopic}
        onCancel={() => setBriefTopic(null)}
        width={760}
        footer={[
          <Button key="cancel" onClick={() => setBriefTopic(null)}>关闭</Button>,
          <Button
            key="brief"
            type="primary"
            loading={workflowMode === 'brief' && workflowTask?.status !== 'completed'}
            onClick={handleGenerateBrief}
          >
            生成创作简报
          </Button>,
          <Button
            key="article"
            disabled={!briefTopic?.brief}
            loading={workflowMode === 'article' && workflowTask?.status !== 'completed'}
            onClick={handleGenerateArticle}
          >
            生成文章
          </Button>,
        ]}
      >
        {briefTopic && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div>
              <Text strong>{briefTopic.title}</Text>
              <div style={{ marginTop: 6 }}>
                <Tag>{briefTopic.platform}</Tag>
                {briefTopic.hot_value != null && <Tag color="orange">{briefTopic.hot_value.toLocaleString()}</Tag>}
              </div>
            </div>

            <Select
              mode="multiple"
              allowClear
              placeholder="Knowledge files (optional scope)"
              value={selectedKnowledgeFileIds}
              onChange={handleKnowledgeFileChange}
              options={readyKnowledgeFiles.map((file) => ({
                value: file.id,
                label: `${file.original_filename} (${file.chunk_count})`,
              }))}
            />

            <Select
              mode="multiple"
              allowClear
              placeholder="Knowledge snippets"
              loading={knowledgeRecommending}
              value={selectedKnowledgeChunkIds}
              onChange={(ids) => {
                setKnowledgeSelectionTouched(true)
                setSelectedKnowledgeChunkIds(ids)
              }}
              options={knowledgeChunkOptions}
            />

            <Select
              mode="multiple"
              allowClear
              placeholder="选择事实资料/案例/数据"
              value={selectedMaterialIds}
              onChange={setSelectedMaterialIds}
              options={(factMaterials ?? []).filter((item) => item.id != null).map((item) => ({
                value: item.id as number,
                label: item.title,
              }))}
            />

            <Select
              allowClear
              placeholder="选择爆款参考文章"
              value={selectedReferenceSlug ?? undefined}
              onChange={(value) => setSelectedReferenceSlug(value ?? null)}
              options={(hotReferences ?? []).map((item) => ({
                value: item.slug,
                label: `${item.title} (${item.read_count})`,
              }))}
            />

            {workflowTaskId && (
              <div>
                <Progress
                  percent={workflowTask?.progress ?? 0}
                  size="small"
                  status={workflowTask?.status === 'failed' ? 'exception' : workflowTask?.status === 'completed' ? 'success' : 'active'}
                />
                {workflowLogs.length > 0 && (
                  <div style={{ maxHeight: 90, overflowY: 'auto', background: '#0d1117', color: '#c9d1d9', padding: '6px 10px', borderRadius: 4, fontSize: 11 }}>
                    {workflowLogs.filter(Boolean).map((line, i) => <div key={i}>{line}</div>)}
                  </div>
                )}
              </div>
            )}

            {briefTopic.brief && (
              <>
                <Divider style={{ margin: '4px 0' }} />
                <Text strong>{briefTopic.brief.recommended_title || '创作简报'}</Text>
                {[
                  ['标题角度', briefTopic.brief.title_angles],
                  ['受众痛点', briefTopic.brief.audience_pain_points],
                  ['文章提纲', briefTopic.brief.outline],
                  ['可用素材', briefTopic.brief.usable_materials],
                  ['风险提醒', briefTopic.brief.risk_notes],
                ].map(([label, items]) => (
                  <div key={label as string}>
                    <Text type="secondary">{label as string}</Text>
                    <List
                      size="small"
                      dataSource={(items as string[]) ?? []}
                      renderItem={(item) => <List.Item style={{ padding: '2px 0' }}>{item}</List.Item>}
                    />
                  </div>
                ))}
              </>
            )}
          </div>
        )}
      </Modal>
    </>
  )
}
