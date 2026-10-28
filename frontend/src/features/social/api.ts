/** social 领域接口：仅封装该领域的数据契约，认证与错误处理由共享 HTTP 客户端负责。 */
import api from "@/lib/http";
import type {
  FriendRequest,
  Friend,
  SocialMessageData,
  SendMessageInput,
} from "@/types";

export async function sendFriendRequest(friendUsername: string): Promise<void> {
  await api.post("/messages/friend-request", {
    friend_username: friendUsername,
  });
}

export async function listFriendRequests(): Promise<FriendRequest[]> {
  const { data } = await api.get("/messages/friend-requests");
  return data;
}

export async function acceptFriendRequest(fid: number): Promise<void> {
  await api.post(`/messages/friend-request/${fid}/accept`);
}

export async function rejectFriendRequest(fid: number): Promise<void> {
  await api.post(`/messages/friend-request/${fid}/reject`);
}

export async function listFriends(): Promise<Friend[]> {
  const { data } = await api.get("/messages/friends");
  return data;
}

export async function sendSocialMessage(
  body: SendMessageInput,
): Promise<SocialMessageData> {
  const { data } = await api.post("/messages/send", body);
  return data;
}

export async function getConversation(
  friendId: number,
  page = 1,
  size = 50,
): Promise<SocialMessageData[]> {
  const { data } = await api.get(`/messages/conversation/${friendId}`, {
    params: { page, size },
  });
  return data;
}

export async function getUnreadCount(): Promise<{ unread: number }> {
  const { data } = await api.get("/messages/unread-count");
  return data;
}
