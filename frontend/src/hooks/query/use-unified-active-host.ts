import { useQueries } from "@tanstack/react-query";
import axios from "axios";
import React from "react";
import { useActiveSandbox } from "./use-active-sandbox";

/**
 * Unified hook to get active web host for both legacy (V0) and V1 conversations
 * - V0: Uses the legacy getWebHosts API endpoint and polls them
 * - V1: Gets worker URLs from sandbox exposed_urls (WORKER_1, WORKER_2, etc.)
 */
export const useUnifiedActiveHost = () => {
  const [activeHost, setActiveHost] = React.useState<string | null>(null);
  const sandboxQuery = useActiveSandbox();
  const exposedUrls = sandboxQuery.data?.exposed_urls || [];
  const hosts =
    exposedUrls
      .filter((url) => url.name.startsWith("WORKER_"))
      .map((url) => url.url) || [];

  // Poll all hosts to find which one is active
  const apps = useQueries({
    queries: hosts.map((host) => ({
      queryKey: ["unified", "hosts", host],
      queryFn: async () => {
        try {
          await axios.get(host);
          return host;
        } catch (e) {
          return "";
        }
      },
      refetchInterval: 3000,
      meta: {
        disableToast: true,
      },
    })),
  });

  const appsData = apps.map((app) => app.data);

  React.useEffect(() => {
    const successfulApp = appsData.find((app) => app);
    setActiveHost(successfulApp || "");
  }, [appsData]);

  // Calculate overall loading state including dependent queries for V1
  const { isLoading } = sandboxQuery;
  return { activeHost, isLoading };
};
