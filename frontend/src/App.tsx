import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import AppLayout from './components/Layout'
import WorkshopPage from './pages/WorkshopPage'
import TopicsPage from './pages/TopicsPage'
import BenchmarksPage from './pages/BenchmarksPage'
import PublishPage from './pages/PublishPage'
import AnalyticsPage from './pages/AnalyticsPage'
import SettingsPage from './pages/SettingsPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to="/workshop" replace />} />
          <Route path="/topics" element={<TopicsPage />} />
          <Route path="/benchmarks" element={<BenchmarksPage />} />
          <Route path="/workshop" element={<WorkshopPage />} />
          <Route path="/publish" element={<PublishPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
