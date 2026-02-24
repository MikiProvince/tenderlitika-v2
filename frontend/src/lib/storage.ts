export const API_KEY_STORAGE = "tenderlitika_api_key";
const API_KEY_EVENT = "tlk-api-key-changed";
export const LLM_PROVIDER_STORAGE = "tenderlitika_llm_provider";
const LLM_PROVIDER_EVENT = "tlk-llm-provider-changed";

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

export function getLlmProvider(): string {
  if (typeof window === "undefined") return "auto";
  return localStorage.getItem(LLM_PROVIDER_STORAGE) || "auto";
}

export function setLlmProvider(provider: string) {
  if (typeof window === "undefined") return;
  const value = provider.trim() || "auto";
  localStorage.setItem(LLM_PROVIDER_STORAGE, value);
  window.dispatchEvent(new Event(LLM_PROVIDER_EVENT));
}

export function subscribeToLlmProvider(callback: () => void): () => void {
  if (typeof window === "undefined") return () => {};

  const onStorage = (event: StorageEvent) => {
    if (event.key === null || event.key === LLM_PROVIDER_STORAGE) {
      callback();
    }
  };

  window.addEventListener("storage", onStorage);
  window.addEventListener(LLM_PROVIDER_EVENT, callback);

  return () => {
    window.removeEventListener("storage", onStorage);
    window.removeEventListener(LLM_PROVIDER_EVENT, callback);
  };
}
