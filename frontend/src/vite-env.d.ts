/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_DATA_SOURCE?: 'mock' | 'lambda'
  readonly VITE_API_URL?: string
  readonly VITE_API_LAMBDA_URL?: string
  readonly VITE_CHAT_LAMBDA_URL?: string
  readonly VITE_INSIGHTS_BUILDER_LAMBDA_URL?: string
  readonly VITE_API_INSIGHTS_PATH?: string
  readonly VITE_CHAT_PATH?: string
  readonly VITE_INSIGHTS_BUILDER_PATH?: string
  readonly VITE_AUTH_TOKEN_STORAGE_KEY?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

declare module '*.png' {
  const src: string
  export default src
}
declare module '*.svg' {
  const src: string
  export default src
}
