/* eslint-disable @typescript-eslint/no-explicit-any */
import { Query, useQuery } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { V1AppConversation } from "#/api/conversation-service/v1-conversation-service.types";
import V1ConversationService from "#/api/conversation-service/v1-conversation-service.api";

const FIVE_MINUTES = 1000 * 60 * 5;
const FIFTEEN_MINUTES = 1000 * 60 * 15;

type RefetchInterval = (
  query: Query<
    V1AppConversation | null,
    AxiosError<unknown, any>,
    V1AppConversation | null,
    (string | null)[]
  >,
) => number;

export const useV1Conversation = (
  conversationId: string | null,
  refetchInterval?: RefetchInterval,
) =>
  useQuery({
    queryKey: ["AppConversation", conversationId],
    queryFn: async () => {
      if (!conversationId) return null;

      const conversations =
        await V1ConversationService.batchGetAppConversations([conversationId]);
      return conversations[0];
    },
    enabled: !!conversationId,
    retry: false,
    refetchInterval,
    staleTime: FIVE_MINUTES,
    gcTime: FIFTEEN_MINUTES,
  });
