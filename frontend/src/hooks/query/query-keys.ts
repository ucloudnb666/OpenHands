/**
 * Centralized query keys for TanStack Query.
 * Using constants ensures type safety and prevents typos.
 */

export const QUERY_KEYS = {
  /** Web client configuration from the server */
  WEB_CLIENT_CONFIG: ["web-client-config"] as const,
} as const;

export type QueryKeys = (typeof QUERY_KEYS)[keyof typeof QUERY_KEYS];
