/** reading 领域接口：仅封装该领域的数据契约，认证与错误处理由共享 HTTP 客户端负责。 */
import api from "@/lib/http";
import type {
  ReadingConfigList,
  ReadingConfigInput,
  ReadingConfig,
  ReadingConfigData,
  ReadBook,
  ReadChapter,
  ReadChapterDetail,
} from "@/types";

export async function listReadingConfigs(): Promise<ReadingConfigList> {
  const { data } = await api.get("/reading-configs");
  return data;
}

export async function createReadingConfig(
  body: ReadingConfigInput,
): Promise<ReadingConfig> {
  const { data } = await api.post("/reading-configs", body);
  return data;
}

export async function exportReadingConfig(
  rcid: number,
): Promise<{ name: string; scene: string; config_json: ReadingConfigData }> {
  const { data } = await api.get(`/reading-configs/${rcid}/export`);
  return data;
}

export async function getBookForRead(bid: number): Promise<ReadBook> {
  const { data } = await api.get(`/community/books/${bid}/read`);
  return data;
}

export async function listChaptersForRead(bid: number): Promise<ReadChapter[]> {
  const { data } = await api.get(`/community/books/${bid}/read/chapters`);
  return data;
}

export async function getChapterForRead(
  bid: number,
  cid: number,
): Promise<ReadChapterDetail> {
  const { data } = await api.get(
    `/community/books/${bid}/read/chapters/${cid}`,
  );
  return data;
}
