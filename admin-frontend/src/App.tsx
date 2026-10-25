import { useEffect, useState, type FormEvent } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Shield, ArrowRight, LogOut, ExternalLink } from 'lucide-react'
import { useAuthStore } from '@/stores/auth'
import { extractError } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import Admin from '@/pages/Admin'
const writerUrl=import.meta.env.VITE_WRITER_URL || 'http://localhost:5173'
function Login(){
 const [username,setUsername]=useState('');const [password,setPassword]=useState('');const [busy,setBusy]=useState(false);const [error,setError]=useState('')
 const login=useAuthStore(s=>s.login);const token=useAuthStore(s=>s.token);const hydrated=useAuthStore(s=>s.hydrated);const qc=useQueryClient()

 const submit=async(e:FormEvent)=>{e.preventDefault();setBusy(true);setError('');try{qc.clear();await login(username,password);window.history.replaceState(null,'','/')}catch(err){setError(extractError(err, err instanceof Error && err.message.startsWith('此账号') ? err.message : '登录失败，请检查账号与密码'))}finally{setBusy(false)}}
 return <div className="min-h-screen grid place-items-center bg-background px-5"><main className="w-full max-w-md"><div className="flex items-center gap-3 mb-10"><span className="p-3 bg-primary text-primary-foreground rounded-xl"><Shield size={24}/></span><div className="font-semibold">StoryClaw<p className="text-xs text-muted-foreground font-normal mt-1">运营中台 · 独立管理入口</p></div></div><section className="bg-card border rounded-2xl p-8 shadow-sm"><h1 className="text-2xl font-semibold">管理员登录</h1><p className="text-sm text-muted-foreground mt-3">管理平台模型、用户、积分与运营记录。</p><form onSubmit={submit} className="space-y-5 mt-8"><div className="space-y-2"><Label htmlFor="admin-user">管理员账号</Label><Input id="admin-user" required value={username} onChange={e=>setUsername(e.target.value)} autoComplete="username"/></div><div className="space-y-2"><Label htmlFor="admin-password">密码</Label><Input id="admin-password" type="password" required value={password} onChange={e=>setPassword(e.target.value)} autoComplete="current-password"/></div>{error && <p role="alert" className="text-sm text-destructive">{error}</p>}<Button type="submit" className="w-full h-11" disabled={busy}>{busy?'正在验证…':'登录运营中台'}<ArrowRight size={16}/></Button></form></section><a className="mt-6 flex items-center justify-center gap-2 text-sm text-muted-foreground" href={writerUrl}>返回创作站 <ExternalLink size={14}/></a></main></div>
}
function Console(){
 const user=useAuthStore(s=>s.user);const hydrated=useAuthStore(s=>s.hydrated);const token=useAuthStore(s=>s.token);const logout=useAuthStore(s=>s.logout);const qc=useQueryClient()
 if(!hydrated) return <p className="p-10">正在验证管理权限…</p>
 if(!token || !user?.is_admin) return <Login/>
 return <div className="min-h-screen"><header className="border-b bg-card px-5 lg:px-10 h-16 flex items-center justify-between"><div className="flex gap-3 items-center"><Shield className="text-primary" size={22}/><span className="font-semibold">StoryClaw <span className="text-muted-foreground font-normal text-sm ml-2">运营中台</span></span></div><div className="flex items-center gap-4"><a href={writerUrl} target="_blank" rel="noreferrer" className="text-sm text-muted-foreground hidden sm:flex items-center gap-1">创作站<ExternalLink size={14}/></a><span className="text-sm">{user.username}</span><Button variant="outline" onClick={()=>{qc.clear();logout()}}><LogOut size={15}/>退出</Button></div></header><main className="max-w-[1500px] mx-auto p-5 lg:p-10"><Admin/></main></div>
}
export default function App(){
 const fetchMe=useAuthStore(s=>s.fetchMe);const token=useAuthStore(s=>s.token);const hydrated=useAuthStore(s=>s.hydrated)
 useEffect(()=>{if(!hydrated){if(token)void fetchMe();else useAuthStore.setState({hydrated:true})}},[token,hydrated,fetchMe])
 const user=useAuthStore(s=>s.user)
 useEffect(()=>{if(hydrated)window.history.replaceState(null,'',token && user?.is_admin ? '/' : '/login')},[hydrated,token,user])
 if(!hydrated)return <p className="p-10">正在验证管理权限…</p>
 return token && user?.is_admin ? <Console/> : <Login/>
}
