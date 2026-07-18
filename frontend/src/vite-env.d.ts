/// <reference types="vite/client" />

// Vite supplies import.meta.env at build time. This declaration lets
// TypeScript understand the environment variables used by the API client.
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
