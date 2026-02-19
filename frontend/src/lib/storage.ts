export const API_KEY_STORAGE = "tenderlitika_api_key";
const API_KEY_EVENT = "tlk-api-key-changed";

export function getApiKey(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(API_KEY_STORAGE);
}

export function setApiKey(key: string) {
  if (typeof window === "undefined") return;
  localStorage.setItem(API_KEY_STORAGE, key.trim());
  window.dispatchEvent(new Event(API_KEY_EVENT));
}

export function clearApiKey() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(API_KEY_STORAGE);
  window.dispatchEvent(new Event(API_KEY_EVENT));
}

export function subscribeToApiKey(callback: () => void): () => void {
  if (typeof window === "undefined") return () => {};

  const onStorage = (event: StorageEvent) => {
    if (event.key === null || event.key === API_KEY_STORAGE) {
      callback();
    }
  };

  window.addEventListener("storage", onStorage);
  window.addEventListener(API_KEY_EVENT, callback);

  return () => {
    window.removeEventListener("storage", onStorage);
    window.removeEventListener(API_KEY_EVENT, callback);
  };
}
