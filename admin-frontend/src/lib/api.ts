import type { AdminUser, CreditsReport } from '@/types'
export const TOKEN_KEY = 'sc_admin_token'
export class ApiError extends Error {
 constructor(public status:number, public body:unknown) { super(`HTTP ${status}`) }
}
async function request<T=unknown>(method:string,path:string,body?:unknown,params?:Record<string,string|number>):Promise<{data:T}> {
 const controller=new AbortController()
 const timer=setTimeout(()=>controller.abort(),60000)
 try {
  const query=params?'?'+new URLSearchParams(Object.entries(params).map(([k,v])=>[k,String(v)])):''
  const token=localStorage.getItem(TOKEN_KEY)
  const response=await fetch('/api/v1'+path+query,{method,signal:controller.signal,headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{})},body:body===undefined?undefined:JSON.stringify(body)})
  const data=await response.json()
  if(!response.ok){
   if(response.status===401){localStorage.removeItem(TOKEN_KEY);if(location.pathname!=='/login')location.replace('/login')}
   throw new ApiError(response.status,data)
  }
  return {data}
 } finally { clearTimeout(timer) }
}
const api={
 get:<T=any>(path:string,options?:{params?:Record<string,string|number>})=>request<T>('GET',path,undefined,options?.params),
 post:<T=any>(path:string,body?:unknown)=>request<T>('POST',path,body),
 put:<T=any>(path:string,body?:unknown)=>request<T>('PUT',path,body),
}
export function extractError(error:unknown,fallback:string):string {
 if(error instanceof ApiError) {
  const body=error.body as {detail?:unknown;message?:unknown;error?:{message?:unknown}}
  if(typeof body?.detail==='string')return body.detail
  if(typeof body?.message==='string')return body.message
  if(typeof body?.error?.message==='string')return body.error.message
 }
 if(error instanceof DOMException && error.name==='AbortError')return '请求超时，请稍后再试'
 return fallback
}
export default api

// ===== P2-10 后台管理 =====
export async function listAdminUsers(page = 1): Promise<AdminUser[]> {
  const { data } = await api.get('/admin/users', {params: {page, limit: 50}})
  return data
}

export async function getCreditsReport(): Promise<CreditsReport> {
  const { data } = await api.get('/admin/credits-report')
  return data
}

export async function getAdminPricing(): Promise<Record<string, unknown>> {
  const { data } = await api.get('/admin/pricing')
  return data
}

export async function updateAdminPricing(body: Record<string, unknown>): Promise<void> {
  await api.put('/admin/pricing', body)
}

export async function getAdminMembership(): Promise<Record<string, unknown>> {
  const { data } = await api.get('/admin/membership')
  return data
}

export async function updateAdminMembership(body: Record<string, unknown>): Promise<void> {
  await api.put('/admin/membership', body)
}

