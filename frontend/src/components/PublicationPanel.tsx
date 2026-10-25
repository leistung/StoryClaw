import {useQuery,useMutation,useQueryClient} from '@tanstack/react-query'
import {Link} from 'react-router-dom'
import {Globe,Lock,ExternalLink} from 'lucide-react'
import {toast} from 'sonner'
import api,{extractError} from '@/lib/api'
import {Button} from './ui/button'
export default function PublicationPanel({bookId}:{bookId:number}){
 const qc=useQueryClient()
 const {data,error}=useQuery({queryKey:['publication',bookId],queryFn:async()=>(await api.get<{visible:boolean;published_at:string|null;chapter_count:number;url:string}>(`/books/${bookId}/publication`)).data})
 const change=useMutation({mutationFn:async(publish:boolean)=>api.post(`/books/${bookId}/publication${publish?'':'/unpublish'}`),onSuccess:(_,publish)=>{qc.invalidateQueries({queryKey:['publication',bookId]});toast.success(publish?'已发布当前正文快照':'作品已转为私密')},onError:e=>toast.error(extractError(e,'操作失败'))})
 return <section className="publication-card"><div className="flex items-center gap-2 font-medium">{data?.visible?<Globe size={18}/>:<Lock size={18}/>}作品可见性<span className="ml-auto text-xs text-primary">{data?.visible?'已公开':'私密草稿'}</span></div><p className="text-xs text-muted-foreground leading-6 my-4">草稿默认仅自己可见。发布会公开当前已保存且有正文的章节快照；后续编辑仍留在草稿，需再次发布才会更新阅读版本。</p>{error&&<p role="alert">{extractError(error,'状态加载失败')}</p>}{data?.published_at&&<p className="text-xs text-muted-foreground mb-4">最近发布 {new Date(data.published_at).toLocaleString('zh-CN')} · {data.chapter_count} 章</p>}<div className="flex flex-wrap gap-2"><Button size="sm" disabled={!data||change.isPending} onClick={()=>{if(window.confirm('确认公开当前已保存的正文？其他用户将能阅读这些章节。'))change.mutate(true)}}>{data?.visible?'更新公开版本':'发布作品'}</Button>{data?.visible&&<><Button size="sm" variant="outline" disabled={change.isPending} onClick={()=>change.mutate(false)}>转为私密</Button><Link className="quiet-action" to={data.url}>阅读预览<ExternalLink size={13}/></Link></>}</div></section>
}
