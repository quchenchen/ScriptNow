import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  // The admin application is hosted below /admin/ in production. Keeping the
  // public base explicit prevents its assets from colliding with the creator
  // SPA assets served from the site root.
  base: '/admin/',
  plugins: [vue()],
  server: { host: '127.0.0.1', port: 5173, proxy: { '/api': { target: 'http://127.0.0.1:8000', rewrite: (path) => path.replace(/^\/api/, '') } } },
})
