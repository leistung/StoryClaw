import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import api, { extractError } from '@/lib/http'
import type { ShareData } from '@/types'
import { Card, CardContent } from '@/components/ui/card'

export default function Share() {
  const { token = '' } = useParams<{ token: string }>()
  const { data, isLoading, error } = useQuery({
    queryKey: ['share', token],
    queryFn: async () => (await api.get<ShareData>(`/share/${token}`)).data,
    enabled: !!token,
  })

  if (isLoading) {
    return (
      <div className="min-h-full flex items-center justify-center text-muted-foreground">
        加载中…
      </div>
    )
  }
  if (error) {
    return (
      <div className="min-h-full flex items-center justify-center text-destructive">
        {extractError(error, '加载失败')}
      </div>
    )
  }
  if (!data) return null

  return (
    <div className="min-h-full bg-muted/40 flex items-center justify-center px-4 py-8">
      <Card className="w-full max-w-2xl border-none shadow-md">
        <CardContent className="p-6">
          <div className="flex items-center justify-between mb-4">
            <h1 className="text-lg font-bold">分享的对话</h1>
            <span className="text-sm text-muted-foreground">
              {new Date(data.created_at).toLocaleString()}
            </span>
          </div>
          <div className="bg-muted rounded-lg p-4 whitespace-pre-wrap break-words text-foreground">
            {data.content}
          </div>
          <div className="mt-4 grid grid-cols-2 gap-2 text-sm text-muted-foreground">
            <div>作者：{data.username}</div>
            <div>模型：{data.model}</div>
            <div>输入 token：{data.in_tokens}</div>
            <div>输出 token：{data.out_tokens}</div>
            <div>消耗积分：{data.credits_cost}</div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
