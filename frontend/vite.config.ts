import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Vite 配置：开发环境代理后端 /api
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
