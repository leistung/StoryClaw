import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Feather, BookOpen, Users, HelpCircle, CreditCard, MessageCircle, Sun, Moon, LogOut, ArrowUpRight, Plus, LayoutDashboard, PanelLeftClose, Menu, Activity } from 'lucide-react'
import { useState } from 'react'
import { useAuthStore } from '@/stores/auth'
import api, { getUnreadCount } from '@/lib/api'
import { useTheme } from '@/components/theme-provider'
import { Button } from '@/components/ui/button'

const links = [
  { to: '/', label: '创作首页', icon: LayoutDashboard },
  { to: '/?view=books', label: '我的作品', icon: BookOpen },
  { to: '/jobs', label: '任务中心', icon: Activity },
  { to: '/community', label: '创作社区', icon: Users },
  { to: '/messages', label: '消息中心', icon: MessageCircle },
]
export default function Layout() {
  const user = useAuthStore(s => s.user)
  const clearAuth = useAuthStore(s => s.logout)
  const qc = useQueryClient()
  const navigate = useNavigate()
  const location = useLocation()
  const { theme, toggle } = useTheme()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [collapsed,setCollapsed]=useState(()=>localStorage.getItem('sc-sidebar-collapsed')==='1')
  const toggleSidebar=()=>setCollapsed(value=>{localStorage.setItem('sc-sidebar-collapsed',value?'0':'1');return !value})
  const { data } = useQuery({ queryKey: ['unread-count', user?.id], queryFn: getUnreadCount, enabled: !!user, refetchInterval: 30000, retry: false })
  const wallet = useQuery({ queryKey: ['wallet'], queryFn: async () => (await api.get<{credits_balance:number}>('/wallet')).data, enabled: !!user, refetchInterval: 10000 })
  const logout = () => { qc.clear(); clearAuth(); navigate('/login') }
  return <div className={`studio-shell ${mobileOpen ? 'sidebar-open' : ''} ${collapsed ? 'sidebar-collapsed' : ''}`}>
    <button className="sidebar-scrim" aria-label="关闭导航" onClick={() => setMobileOpen(false)} />
    <aside className="studio-sidebar">
      <div className="sidebar-brand-row"><NavLink to="/" className="studio-brand" title="StoryClaw 首页"><span className="brand-mark"><Feather size={23}/></span><span className="brand-copy">StoryClaw<small>创作，让故事生长</small></span></NavLink><button className="sidebar-toggle" onClick={toggleSidebar} aria-label={collapsed?'展开侧边栏':'收起侧边栏'} aria-expanded={!collapsed} title={collapsed?'展开侧边栏':'收起侧边栏'}><PanelLeftClose size={16}/></button></div>
      <button className="studio-new" aria-label="新建作品" title="新建作品" onClick={() => { navigate('/?new=1'); setMobileOpen(false) }}><Plus size={17} /><span className="new-label">新建作品</span><span className="new-extra">＋</span></button>
      <div className="sidebar-nav-scroll"><p className="nav-caption">工作空间</p>
      <nav className="studio-navigation">{links.map(item => {
        const active = item.to === '/?view=books' ? location.pathname === '/' && location.search.includes('view=books') : item.to === '/' ? location.pathname === '/' && !location.search.includes('view=books') : location.pathname.startsWith(item.to)
        return <NavLink key={item.to} to={item.to} title={item.label} onClick={() => setMobileOpen(false)} className={active ? 'is-active' : ''}><item.icon size={18} /><span>{item.label}</span>{item.to === '/messages' && !!data?.unread && <b className="unread-pill">{data.unread}</b>}</NavLink>
      })}</nav>
      <p className="nav-caption mt-7">支持与服务</p>
      <nav className="studio-navigation"><NavLink to="/recharge" title="会员与积分" className={({isActive})=>isActive?"is-active":""} onClick={() => setMobileOpen(false)}><CreditCard size={18} /><span>会员与积分</span></NavLink><NavLink to="/help" title="使用指南" className={({isActive})=>isActive?"is-active":""} onClick={() => setMobileOpen(false)}><HelpCircle size={18} /><span>使用指南</span><ArrowUpRight size={13} className="ml-auto" /></NavLink></nav>
      </div><div className="sidebar-bottom"><div className="credits-panel"><div><span className="status-dot" /> 灵感续航</div><strong>{(wallet.data?.credits_balance ?? user?.credits_balance ?? 0).toLocaleString()} <small>积分可用</small></strong><NavLink to="/recharge">为下一个好故事做好准备 <ArrowUpRight size={14} /></NavLink></div>
      <div className="sidebar-user"><span className="user-monogram">{user?.username.slice(0,1).toUpperCase()}</span><div><strong>{user?.username}</strong><small>{user?.is_admin ? '管理员 · 创作者' : '创作者'}</small></div><button aria-label="退出登录" onClick={logout}><LogOut size={16} /></button></div></div>
    </aside>
    <div className="studio-main"><header className="studio-topbar"><div className="flex items-center gap-3"><button className="md:hidden" aria-label="打开导航" onClick={() => setMobileOpen(true)}><Menu size={20} /></button><span className="topbar-breadcrumb">工作空间 <span>/</span> {location.pathname === '/' ? '创作工作台' : links.find(x => x.to === location.pathname)?.label || ({'/help':'使用指南','/recharge':'会员与积分'}[location.pathname] ?? 'StoryClaw')}</span></div><div className="flex items-center gap-3"><span className="studio-ready"><span className="status-dot" /> 为你的下一章准备就绪</span><Button size="icon" variant="ghost" onClick={toggle} aria-label="切换主题">{theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}</Button><NavLink to="/help" title="使用指南" className="topbar-help">帮助中心 <ArrowUpRight size={13}/></NavLink></div></header><main className="studio-content"><Outlet /></main></div>
  </div>
}
