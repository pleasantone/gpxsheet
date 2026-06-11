/// <reference types="vite/client" />

declare global {
  interface Window {
    // Signed first-party token injected into index.html by the backend when the
    // deployment gates its API; sent as the X-First-Party header by the SPA.
    __GPXSHEET_FP__?: string;
  }
}

export {};
