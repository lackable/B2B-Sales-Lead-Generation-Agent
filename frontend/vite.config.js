import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  envDir: '..',
  resolve: {
    dedupe: ['react', 'react-dom'],
  },
  server: {
    allowedHosts: true,
    fs: {
      allow: ['..'],
    },
  },
})
