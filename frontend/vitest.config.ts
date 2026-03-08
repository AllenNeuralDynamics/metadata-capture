import { defineConfig } from 'vitest/config';
import path from 'path';

export default defineConfig({
  // Next.js injects `import React` at build time; vitest doesn't unless told.
  esbuild: {
    jsx: 'automatic',
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './app'),
    },
  },
});
