import { create } from 'zustand'
import api, { TOKEN_KEY } from '@/lib/api'
type Admin = {id:number;username:string;is_admin:boolean;credits_balance:number}
type AuthState = {user:Admin|null;token:string|null;hydrated:boolean;login:(username:string,password:string)=>Promise<void>;logout:()=>void;fetchMe:()=>Promise<void>}
export const useAuthStore=create<AuthState>((set)=>({
 user:null,token:localStorage.getItem(TOKEN_KEY),hydrated:false,
 login:async(username,password)=>{
  const {data}=await api.post('/auth/login',{username,password})
  if(!data.user.is_admin) throw new Error('此账号没有运营中台权限，请使用管理员账号登录')
  localStorage.setItem(TOKEN_KEY,data.token)
  set({user:data.user,token:data.token,hydrated:true})
 },
 logout:()=>{localStorage.removeItem(TOKEN_KEY);set({user:null,token:null,hydrated:true})},
 fetchMe:async()=>{
  try {const {data}=await api.get<Admin>('/auth/me');if(!data.is_admin)throw new Error('没有管理员权限');set({user:data,hydrated:true})}
  catch {localStorage.removeItem(TOKEN_KEY);set({user:null,token:null,hydrated:true})}
 }
}))
