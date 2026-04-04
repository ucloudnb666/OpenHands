import { useQuery } from "@tanstack/react-query";
import EventService from "#/api/event-service/event-service.api";
import { useUserConversation } from "#/hooks/query/use-user-conversation";
import { OpenHandsEvent } from "#/types/v1/core";

export interface ConversationHistoryResult {
  events: OpenHandsEvent[];
  /**
   * The oldest timestamp from preloaded events, used for WebSocket handoff.
   * WebSocket should use after_timestamp to only receive events newer than this.
   */
  oldestTimestamp: string | null;
}

export const useConversationHistory = (conversationId?: string) => {
  const { data: conversation } = useUserConversation(conversationId ?? null);
  const conversationVersion = conversation?.conversation_version;

  return useQuery({
    queryKey: ["conversation-history", conversationId, conversationVersion],
    enabled: !!conversationId && !!conversation,
    queryFn: async (): Promise<ConversationHistoryResult> => {
      if (!conversationId || !conversationVersion) {
        return { events: [], oldestTimestamp: null };
      }

      if (conversationVersion === "V1") {
        // Fetch newest events first for instant perceived load
        // User sees current conversation state immediately
        const result = await EventService.searchEventsV1(conversationId, {
          sort_order: "TIMESTAMP_DESC",
          limit: 100,
        });

        // Extract oldest timestamp for WebSocket handoff
        // WebSocket will only send events after this timestamp
        const oldestTimestamp =
          result.items.length > 0
            ? result.items[result.items.length - 1].timestamp
            : null;

        return {
          events: result.items,
          oldestTimestamp,
        };
      }

      // V0 conversations - legacy behavior (no bi-directional loading)
      const events = await EventService.searchEventsV0(conversationId);
      return { events, oldestTimestamp: null };
    },
    staleTime: Infinity,
    gcTime: 30 * 60 * 1000, // 30 minutes — survive navigation away and back (AC5)
  });
};
