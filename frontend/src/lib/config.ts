declare global {
  interface Window {
    __TELEGRAM_AUTO_POSTER__?: {
      botUsername?: string;
      defaultLanguage?: string;
    };
  }
}

export function getPublicConfig() {
  return window.__TELEGRAM_AUTO_POSTER__ ?? {};
}
