import { lazy, Suspense, useEffect } from 'react'
import { Routes, Route, Navigate, useLocation, useParams } from 'react-router-dom'
import { useAuthStore } from '@/stores/auth'
import Layout from '@/components/Layout'
import type { ReactNode } from 'react'

// 路由级懒加载：按页面拆分 chunk，首页只加载必要的代码
const Home = lazy(() => import('@/pages/Home'))
const Login = lazy(() => import('@/pages/Login'))
const Register = lazy(() => import('@/pages/Register'))
const Share = lazy(() => import('@/pages/Share'))
const Workspace = lazy(() => import('@/pages/Workspace'))
const Community = lazy(() => import('@/pages/Community'))
const PostDetail = lazy(() => import('@/pages/PostDetail'))
const ReadBook = lazy(() => import('@/pages/ReadBook'))
const Help = lazy(() => import('@/pages/Help'))
const Recharge = lazy(() => import('@/pages/Recharge'))
const Jobs = lazy(() => import('@/features/jobs/components/JobCenter'))
const Messages = lazy(() => import('@/pages/Messages'))

function AdminRedirect() {
  useEffect(() => { window.location.replace(import.meta.env.VITE_ADMIN_URL || 'http://localhost:5174') }, [])
  return <div className="p-8">正在打开独立运营中台…</div>
}

const PageFallback = () => (
  <div className="flex min-h-[60vh] items-center justify-center">
    <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
  </div>
)

// ReadBook 接收 { bookId: number } prop，路由层用 useParams 转换
function ReadBookRoute() {
  const { bookId } = useParams<{ bookId: string }>()
  return <ReadBook bookId={Number(bookId)} />
}

function Protected({ children }: { children: ReactNode }) {
  const token = useAuthStore((s) => s.token)
  const hydrated = useAuthStore((s) => s.hydrated)
  const location = useLocation()
  if (!hydrated) {
    return <div className="p-8 text-gray-500">加载中…</div>
  }
  if (!token) {
    const from = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?from=${from}`} replace />
  }
  return <>{children}</>
}

export default function App() {
  const token = useAuthStore((s) => s.token)
  const hydrated = useAuthStore((s) => s.hydrated)
  const fetchMe = useAuthStore((s) => s.fetchMe)

  useEffect(() => {
    if (token && !hydrated) {
      void fetchMe()
    } else if (!token && !hydrated) {
      useAuthStore.setState({ hydrated: true })
    }
  }, [token, hydrated, fetchMe])

  return (
    <Suspense fallback={<PageFallback />}>
      <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/share/:token" element={<Protected><Share /></Protected>} />
      {/* 主页框架：未登录/已登录共用顶部导航，内容按登录态渲染 */}
      <Route element={<Protected><Layout /></Protected>}>
        <Route path="/" element={<Home />} />
        <Route path="/jobs" element={<Jobs />} />
        <Route path="/community" element={<Community />} />
        <Route path="/post/:id" element={<PostDetail />} />
        <Route path="/read/:bookId" element={<ReadBookRoute />} />
        <Route path="/help" element={<Help />} />
        {/* 需要登录的页面 */}
        <Route path="/llm-configs" element={<AdminRedirect />} />
        <Route path="/admin" element={<AdminRedirect />} />
        <Route path="/recharge" element={<Protected><Recharge /></Protected>} />
        <Route path="/messages" element={<Protected><Messages /></Protected>} />
      </Route>
      {/* 工作区（独立页面，无主页导航） */}
      <Route
        path="/workspace/:bookId"
        element={
          <Protected>
            <Workspace />
          </Protected>
        }
      />
      <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </Suspense>
  )
}
