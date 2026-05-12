import { Grid, Layout, Menu } from 'antd'
import {
  BulbOutlined,
  DatabaseOutlined,
  EditOutlined,
  SendOutlined,
  BarChartOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import { useNavigate, useLocation, Outlet } from 'react-router-dom'

const { Sider, Content } = Layout
const { useBreakpoint } = Grid

const navItems = [
  { key: '/topics', icon: <BulbOutlined />, label: '选题库' },
  { key: '/benchmarks', icon: <DatabaseOutlined />, label: '素材库' },
  { key: '/workshop', icon: <EditOutlined />, label: '文章工坊' },
  { key: '/publish', icon: <SendOutlined />, label: '发布中心' },
  { key: '/analytics', icon: <BarChartOutlined />, label: '数据看板' },
  { key: '/settings', icon: <SettingOutlined />, label: '设置' },
]

export default function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const screens = useBreakpoint()
  const isMobile = !screens.md

  const selectedKey =
    navItems.find((item) => location.pathname.startsWith(item.key))?.key ?? '/workshop'

  const title = (
    <div
      style={{
        height: isMobile ? 52 : 64,
        display: 'flex',
        alignItems: 'center',
        padding: isMobile ? '0 16px' : '0 0 0 24px',
        color: '#fff',
        fontSize: 16,
        fontWeight: 600,
        letterSpacing: 0,
        borderBottom: '1px solid rgba(255,255,255,0.08)',
        flexShrink: 0,
      }}
    >
      公众号内容平台
    </div>
  )

  return (
    <Layout style={{ minHeight: '100vh' }}>
      {isMobile ? (
        <div
          style={{
            background: '#001529',
            position: 'sticky',
            top: 0,
            zIndex: 100,
            width: '100%',
          }}
        >
          {title}
          <Menu
            theme="dark"
            mode="horizontal"
            selectedKeys={[selectedKey]}
            items={navItems}
            onClick={({ key }) => navigate(key)}
            style={{
              borderBottom: 0,
              overflowX: 'auto',
              whiteSpace: 'nowrap',
              minWidth: 0,
            }}
          />
        </div>
      ) : (
        <Sider
          width={220}
          style={{
            background: '#001529',
            position: 'fixed',
            left: 0,
            top: 0,
            bottom: 0,
            zIndex: 100,
            overflow: 'auto',
          }}
        >
          {title}
          <Menu
            theme="dark"
            mode="inline"
            selectedKeys={[selectedKey]}
            items={navItems}
            onClick={({ key }) => navigate(key)}
            style={{ marginTop: 8, borderRight: 0 }}
          />
        </Sider>
      )}
      <Layout style={{ marginLeft: isMobile ? 0 : 220 }}>
        <Content
          style={{
            minHeight: isMobile ? 'calc(100vh - 98px)' : '100vh',
            background: '#f5f5f5',
            padding: isMobile ? 12 : 24,
            overflowX: 'hidden',
          }}
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
