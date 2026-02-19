import { Provider } from "#/types/settings";

// Providers used for authentication only — no git repository operations supported
const AUTH_ONLY_PROVIDERS = new Set<Provider>(["enterprise_sso"]);

export const convertRawProvidersToList = (
  raw: Partial<Record<Provider, string | null>> | undefined,
): Provider[] => {
  if (!raw) return [];
  const list: Provider[] = [];
  for (const key of Object.keys(raw)) {
    if (key && !AUTH_ONLY_PROVIDERS.has(key as Provider)) {
      list.push(key as Provider);
    }
  }
  return list;
};
