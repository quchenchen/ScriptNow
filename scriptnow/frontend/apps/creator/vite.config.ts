import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 5174,
    proxy: { '/api': { target: 'http://127.0.0.1:8000', rewrite: (path) => path.slice(4) }, '/files': { target: 'http://127.0.0.1:8000' } },
  },
})
