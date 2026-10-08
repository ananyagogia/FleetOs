import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'


export default defineConfig({
  plugins: [react()],
  se
    port: 3000, 
    host: true,
    open: false,
  },
  preview: {
    port: 3000,
  }
})
