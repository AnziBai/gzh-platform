import { Layout, Menu } from 'antd'
import {
  BulbOutlined,
  DatabaseOutlined,
  EditOutlined,
  SendOutlined,
  BarChartOutlined,
} from '@ant-design/icons'
import { useNavigate, useLocation, Outlet } from 'react-router-dom'

const { Sider, Content } = Layout

const navItems = [
  { key: '/topics', icon: <BulbOutlined />, label: '选题库' },
  { key: '/benchmarks', icon: <DatabaseOutlined />, label: '素材库' },
  { key: '/workshop', icon: <EditOutlined />, label: '文章工坊' },
  { key: '/publish', icon: <SendOutlined />, label: '发布中心' },
  { key: '/analytics', icon: <BarChartOutlined />, label: '数据看板' },
]

export default function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()

  const selectedKey =
    navItems.find((item) => location.pathname.startsWith(item.key))?.key ?? '/workshop'

  return (
    <Layout style={{ minHeight: '100vh' }}>
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
        <div
          style={{
            height: 64,
            display: 'flex',
            alignItems: 'center',
            paddingLeft: 24,
            color: '#fff',
            fontSize: 16,
            fontWeight: 600,
            letterSpacing: 0.5,
            borderBottom: '1px solid rgba(255,255,255,0.08)',
          }}
        >
          公众号内容平台
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={navItems}
          onClick={({ key }) => navigate(key)}
          style={{ marginTop: 8, borderRight: 0 }}
        />
      </Sider>
      <Layout style={{ marginLeft: 220 }}>
        <Content
          style={{
            minHeight: '100vh',
            background: '#f5f5f5',
            padding: 24,
          }}
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
