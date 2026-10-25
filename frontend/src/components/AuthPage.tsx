import { useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Feather, ArrowRight, BookOpen, Network, Sparkles } from 'lucide-react'
import api, { extractError } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import type { AuthResponse } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

export default function AuthPage({ mode }: { mode: 'login' | 'register' }) {
  const registering = mode === 'register'
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const qc = useQueryClient()
  const setAuth = useAuthStore(s => s.setAuth)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setLoading(true); setError('')
    try {
      const result = await api.post<AuthResponse>(registering ? '/auth/register' : '/auth/login', { username, password })
      if (registering) { navigate('/login?registered=1'); return }
      qc.clear()
      setAuth(result.data.user, result.data.token)
      const from = params.get('from') || '/'
      navigate(from.startsWith('/') && !from.startsWith('//') ? from : '/')
    } catch (err) { setError(extractError(err, registering ? '注册失败' : '登录失败')) }
    finally { setLoading(false) }
  }
  return <div className="auth-studio min-h-screen grid lg:grid-cols-2 bg-background">
    <aside className="auth-story-panel hidden lg:flex flex-col justify-between text-[#f4f1e8] p-12 xl:p-20">
      <div className="flex items-center gap-3 text-xl font-semibold"><Feather /> StoryClaw</div>
      <div className="max-w-lg"><span className="text-xs tracking-[.25em] text-emerald-200/70">YOUR NEXT CHAPTER</span>
        <h1 className="text-5xl xl:text-6xl leading-tight font-serif mt-6">让故事生长，<br />让灵感成章。</h1>
        <p className="text-white/60 leading-8 mt-7">从一个人物、一段灵感，到一部完整的小说。在同一个工作台里，规划、创作，并保持故事的一致性。</p>
        <div className="grid grid-cols-3 gap-4 mt-12 border-t border-white/15 pt-7">{[[BookOpen, '作品与章节'], [Sparkles, 'AI 协同写作'], [Network, '故事记忆']].map(([Icon, title]) => { const I = Icon as typeof BookOpen; return <div key={String(title)} className="space-y-3"><I size={20} className="text-emerald-200" /><div className="text-sm text-white/80">{String(title)}</div></div> })}</div>
      </div><p className="text-xs text-white/40">为长篇创作而设计</p>
    </aside>
    <main className="flex items-center justify-center px-6 py-16"><div className="w-full max-w-sm">
      <div className="lg:hidden flex gap-2 items-center font-semibold mb-12"><Feather /> StoryClaw</div>
      <p className="text-primary text-sm mb-3">你的创作空间</p><h2 className="text-3xl font-semibold tracking-tight">{registering ? '开启你的故事' : '欢迎回来'}</h2>
      <p className="text-muted-foreground text-sm mt-3">{registering ? '创建账号，开始管理作品与 AI 创作。' : '登录后继续上一次的灵感。'}</p>
      {!registering && params.get('registered') && <p role="status" className="mt-5 text-sm text-primary">注册成功，请使用新账号登录。</p>}
      <form onSubmit={submit} className="space-y-5 mt-9">
        <div className="space-y-2"><Label htmlFor="username">用户名</Label><Input id="username" autoComplete="username" required minLength={3} maxLength={64} value={username} onChange={e => setUsername(e.target.value)} placeholder="输入用户名" className="h-11" /></div>
        <div className="space-y-2"><Label htmlFor="password">密码</Label><Input id="password" type="password" autoComplete={registering ? 'new-password' : 'current-password'} required minLength={registering ? 6 : 1} maxLength={72} value={password} onChange={e => setPassword(e.target.value)} placeholder={registering ? '至少 6 个字符' : '输入密码'} className="h-11" /></div>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <Button type="submit" disabled={loading} className="w-full h-11">{loading ? '请稍候…' : registering ? '创建账号' : '登录工作台'}<ArrowRight size={16} /></Button>
      </form>
      <p className="mt-7 text-sm text-muted-foreground">{registering ? '已有账号？' : '还没有账号？'} <Link className="text-primary font-medium" to={registering ? '/login' : '/register'}>{registering ? '去登录' : '创建账号'}</Link></p>
    </div></main>
  </div>
}
