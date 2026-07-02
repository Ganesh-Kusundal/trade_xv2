/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_KEY?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_REQUIRE_API?: string
  readonly VITE_API_KEY?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
