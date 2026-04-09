import { useConversationId } from "#/hooks/use-conversation-id";
import { useV1Conversation } from "./use-v1-conversation";

export const useActiveV1Conversation = () => {
  const { conversationId } = useConversationId();
  // Don't poll if this is a task ID (format: "task-{uuid}")
  // Task polling is handled by useTaskPolling hook
  const isTaskId = conversationId.startsWith("task-");
  const actualConversationId = isTaskId ? null : conversationId;
  return useV1Conversation(actualConversationId);
};
