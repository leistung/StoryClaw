/** 共享传输层：统一认证、超时和错误提取，不承载创作或页面业务。 */
import axios, { AxiosError } from "axios";

export const TOKEN_KEY = "sc_token";

export const API_PREFIX = "/api/v1";

const api = axios.create({
  baseURL: API_PREFIX,
  headers: { "Content-Type": "application/json" },
  timeout: 60000,
});

// 请求拦截器：附加 Bearer token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 响应拦截器：401 清 token 跳 /login
api.interceptors.response.use(
  (res) => res,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY);
      const path = location.pathname;
      if (!path.startsWith("/login") && !path.startsWith("/share/")) {
        const from = encodeURIComponent(path + location.search);
        location.href = `/login?from=${from}`;
      }
    }
    return Promise.reject(error);
  },
);

// 友好的错误信息提取
export function extractError(err: unknown, fallback: string): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data;
    if (data) {
      if (typeof data === "string") return data;
      if (typeof data === "object" && data !== null) {
        const d = data as Record<string, unknown>;
        // 统一错误格式：{ error: { code, message, details } }
        if (typeof d.error === "object" && d.error !== null) {
          const e = d.error as Record<string, unknown>;
          if (typeof e.message === "string") return e.message;
        }
        if (typeof d.detail === "string") return d.detail;
        if (Array.isArray(d.detail) && d.detail.length) {
          const first = d.detail[0];
          if (
            first &&
            typeof first === "object" &&
            "msg" in first &&
            typeof (first as { msg: unknown }).msg === "string"
          ) {
            return (first as { msg: string }).msg;
          }
        }
        if (typeof d.message === "string") return d.message;
      }
    }
    if (err.message) return err.message;
  } else if (err instanceof Error) {
    return err.message;
  }
  return fallback;
}

export default api;
