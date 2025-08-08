import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
  ],
  server: {
    proxy: {
      '/api': {
        target: 'http://192.168.4.1:80', // 替换为你的API服务器地址
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '/api/')
      }
    }
  }
})
