import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/static/wc-grid/',
  build: {
    outDir: '../static/wc-grid',
    emptyOutDir: true,
  },
})
