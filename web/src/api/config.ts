/** Runtime configuration sourced from Vite env vars (see .env.example). */

export const API_BASE: string =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export const WS_BASE: string =
  (import.meta.env.VITE_WS_BASE as string | undefined) ?? "";

export const API_KEY: string | undefined =
  (import.meta.env.VITE_API_KEY as string | undefined) || undefined;
