/* eslint-disable @typescript-eslint/no-explicit-any */
import { Query, useQuery } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { V1SandboxInfo } from "#/api/sandbox-service/sandbox-service.types";
import { SandboxService } from "#/api/sandbox-service/sandbox-service.api";

const FIVE_MINUTES = 1000 * 60 * 5;
const FIFTEEN_MINUTES = 1000 * 60 * 15;

type RefetchInterval = (
  query: Query<
    V1SandboxInfo | null,
    AxiosError<unknown, any>,
    V1SandboxInfo | null,
    (string | null)[]
  >,
) => number;

export const useSandbox = (
  sandboxId: string | null,
  refetchInterval?: RefetchInterval,
) =>
  useQuery({
    queryKey: ["sandbox", sandboxId],
    queryFn: async () => {
      if (!sandboxId) return null;

      const sandboxes = await SandboxService.batchGetSandboxes([sandboxId]);
      return sandboxes[0];
    },
    enabled: !!sandboxId,
    retry: false,
    refetchInterval,
    staleTime: FIVE_MINUTES,
    gcTime: FIFTEEN_MINUTES,
  });
