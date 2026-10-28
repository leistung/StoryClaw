/** workspace 领域接口：仅封装该领域的数据契约，认证与错误处理由共享 HTTP 客户端负责。 */
import api from "@/lib/http";
import type {
  ConfigEntityList,
  ConfigEntityInput,
  ConfigEntity,
} from "@/types";

export async function listConfigEntities(
  bid: number,
  entityType: string,
): Promise<ConfigEntityList> {
  const { data } = await api.get(`/books/${bid}/config/${entityType}`);
  return data;
}

export async function createConfigEntity(
  bid: number,
  entityType: string,
  body: ConfigEntityInput,
): Promise<ConfigEntity> {
  const { data } = await api.post(`/books/${bid}/config/${entityType}`, body);
  return data;
}

export async function updateConfigEntity(
  bid: number,
  entityType: string,
  eid: number,
  body: Partial<ConfigEntityInput> & { sort_order?: number },
): Promise<ConfigEntity> {
  const { data } = await api.put(
    `/books/${bid}/config/${entityType}/${eid}`,
    body,
  );
  return data;
}

export async function deleteConfigEntity(
  bid: number,
  entityType: string,
  eid: number,
): Promise<{ ok: boolean; id: number }> {
  const { data } = await api.delete(
    `/books/${bid}/config/${entityType}/${eid}`,
  );
  return data;
}
