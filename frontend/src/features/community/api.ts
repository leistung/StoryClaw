/** community 领域接口：仅封装该领域的数据契约，认证与错误处理由共享 HTTP 客户端负责。 */
import api from "@/lib/http";
import type { PostList, Post, PostInput, SearchResult } from "@/types";

export async function listPosts(page = 1, size = 20): Promise<PostList> {
  const { data } = await api.get("/community/posts", {
    params: { page, size },
  });
  return data;
}

export async function getPost(pid: number): Promise<Post> {
  const { data } = await api.get(`/community/posts/${pid}`);
  return data;
}

export async function createPost(body: PostInput): Promise<Post> {
  const { data } = await api.post("/community/posts", body);
  return data;
}

export async function updatePost(
  pid: number,
  body: Partial<PostInput>,
): Promise<Post> {
  const { data } = await api.put(`/community/posts/${pid}`, body);
  return data;
}

export async function deletePost(pid: number): Promise<void> {
  await api.delete(`/community/posts/${pid}`);
}

export async function searchCommunity(q: string): Promise<SearchResult> {
  const { data } = await api.get("/community/search", { params: { q } });
  return data;
}
