import { fileURLToPath, URL } from 'node:url'

import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueJsx from '@vitejs/plugin-vue-jsx'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // 加载环境变量 (第三个参数为空字符串表示加载所有环境变量,不只是VITE_开头的)
  const env = loadEnv(mode, process.cwd(), '')
  const backendPort = env.BACKEND_API_PORT || '5001'  // 后端API端口,默认5001

  return {
    base: '/', // 确保在生产环境中，静态资源的路径是相对于根目录的
    plugins: [
      vue(),
      vueJsx(),
      vueDevTools(),
    ],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url))
      },
    },
    server: {
      host: '0.0.0.0', // 允许外部访问
      proxy: {
        '/api': {
          target: `http://127.0.0.1:${backendPort}`, // 后端API端口
          changeOrigin: true,
          // rewrite: (path) => path.replace(/^\/api/, ''), // 如果后端 API 没有 /api 前缀，则需要重写
        },
      },
    },
  }
})
