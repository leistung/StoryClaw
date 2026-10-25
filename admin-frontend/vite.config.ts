import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
export default defineConfig({
 plugins:[react()], resolve:{alias:{'@':path.resolve(__dirname,'./src')}},
 server:{host:true,port:5174,strictPort:true,watch:{usePolling:process.env.VITE_USE_POLLING==='true',interval:500},proxy:{'/api':{target:process.env.VITE_PROXY_TARGET || 'http://localhost:8010',changeOrigin:true}}}
})
