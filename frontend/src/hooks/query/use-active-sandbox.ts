import { useActiveV1Conversation } from "./use-active-v1-conversation";
import { useSandbox } from "./use-sandbox";

export const useActiveSandbox = () => {
  const conversationQuery = useActiveV1Conversation();
  const sandboxQuery = useSandbox(conversationQuery?.data?.sandbox_id || null);
  return {
    data: sandboxQuery.data,
    isError: conversationQuery.isError || sandboxQuery.isError,
    isLoading: conversationQuery.isLoading || sandboxQuery.isLoading,
    isFetching: conversationQuery.isFetching || sandboxQuery.isFetching,
    isFetched: sandboxQuery.isFetched,
    error: conversationQuery.error || sandboxQuery.error,
  };
};
