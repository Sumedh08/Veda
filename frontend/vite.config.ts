import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: { host: '127.0.0.1', port: 5173 },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('/node_modules/@supabase/')) return 'auth';
          if (id.includes('/node_modules/react-markdown/') || id.includes('/node_modules/remark-') || id.includes('/node_modules/unified/') || id.includes('/node_modules/mdast-') || id.includes('/node_modules/hast-') || id.includes('/node_modules/vfile')) return 'markdown';
          if (id.includes('/node_modules/lucide-react/')) return 'icons';
          if (id.includes('/node_modules/react/') || id.includes('/node_modules/react-dom/') || id.includes('/node_modules/scheduler/')) return 'react-vendor';
        },
      },
    },
  },
});

