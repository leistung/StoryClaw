import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// Docker 部署时通过 VITE_PROXY_TARGET=http://backend:8000 指向容器网络内的 backend；
// 本机直接 npm run dev 时默认 localhost:8000。
const proxyTarget = process.env.VITE_PROXY_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    watch: { usePolling: process.env.VITE_USE_POLLING === 'true', interval: 500 },
    proxy: { '/api': { target: proxyTarget, changeOrigin: true } },
  },
})
