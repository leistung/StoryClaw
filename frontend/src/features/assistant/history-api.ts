/** assistant 领域接口：仅封装该领域的数据契约，认证与错误处理由共享 HTTP 客户端负责。 */
import api from "@/lib/http";
import type { ChatSession, ChatMessage } from "@/types";

export async function listChatSessions(): Promise<ChatSession[]> {
  const res = await api.get<ChatSession[]>("/chat/sessions");
  return res.data;
}

export async function getChatMessages(
  threadId: string,
): Promise<ChatMessage[]> {
  const res = await api.get<ChatMessage[]>("/messages", {
    params: { thread_id: threadId },
  });
  return res.data;
}
