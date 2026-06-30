import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// Vite 配置：开发环境代理后端 /api
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
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
    rollupOptions: {
      output: {
        // P1: 分包策略——按依赖类型拆分,降低首屏 chunk 体积
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          // react 核心
          if (id.includes('/node_modules/react/') || id.includes('/node_modules/react-dom/') || id.includes('/node_modules/scheduler/')) {
            return 'vendor-react'
          }
          // reactflow 画布引擎(独立大依赖,仅 editor 视图使用)
          if (id.includes('/node_modules/reactflow/') || id.includes('/node_modules/dagre/') || id.includes('/node_modules/cytoscape/') || id.includes('/node_modules/@dagrejs/')) {
            return 'vendor-reactflow'
          }
          // Radix UI 原语(大量小组件合并)
          if (id.includes('/node_modules/@radix-ui/')) {
            return 'vendor-ui'
          }
          // framer-motion 动画
          if (id.includes('/node_modules/framer-motion/') || id.includes('/node_modules/motion-dom/') || id.includes('/node_modules/motion-utils/')) {
            return 'vendor-motion'
          }
          // 图标库
          if (id.includes('/node_modules/lucide-react/')) {
            return 'vendor-icons'
          }
          // cmdk 命令面板
          if (id.includes('/node_modules/cmdk/')) {
            return 'vendor-cmdk'
          }
          // 通用工具库
          if (id.includes('/node_modules/clsx/') || id.includes('/node_modules/class-variance-authority/') || id.includes('/node_modules/tailwind-merge/') || id.includes('/node_modules/axios/')) {
            return 'vendor-utils'
          }
        },
      },
    },
  },
})
