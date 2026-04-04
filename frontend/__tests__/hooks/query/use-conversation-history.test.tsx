import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import React from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { useConversationHistory } from "#/hooks/query/use-conversation-history";
import EventService from "#/api/event-service/event-service.api";
import { useUserConversation } from "#/hooks/query/use-user-conversation";
import type { Conversation } from "#/api/open-hands.types";
import type { OpenHandsEvent } from "#/types/v1/core";

function makeConversation(version: "V0" | "V1"): Conversation {
  return {
    conversation_id: "conv-test",
    title: "Test Conversation",
    selected_repository: null,
    selected_branch: null,
    git_provider: null,
    last_updated_at: new Date().toISOString(),
    created_at: new Date().toISOString(),
    status: "RUNNING",
    runtime_status: null,
    url: null,
    session_api_key: null,
    conversation_version: version,
  };
}

function makeEvent(timestamp?: string): OpenHandsEvent {
  return {
    id: "evt-1",
    timestamp: timestamp ?? "2026-01-15T10:00:00Z",
  } as OpenHandsEvent;
}

// --------------------
// Mocks
// --------------------
vi.mock("#/api/open-hands-axios", () => ({
  openHands: {
    get: vi.fn(),
  },
}));

vi.mock("#/api/event-service/event-service.api");
vi.mock("#/hooks/query/use-user-conversation");

const queryClient = new QueryClient();

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

// --------------------
// Tests
// --------------------
describe("useConversationHistory", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("calls V1 REST endpoint for V1 conversations with TIMESTAMP_DESC", async () => {
    const v1SearchEventsSpy = vi.spyOn(EventService, "searchEventsV1");

    vi.mocked(useUserConversation).mockReturnValue({
      data: makeConversation("V1"),
      isLoading: false,
      isPending: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as any);

    v1SearchEventsSpy.mockResolvedValue({
      items: [makeEvent("2026-01-15T12:00:00Z"), makeEvent("2026-01-15T10:00:00Z")],
      next_page_id: undefined,
    });

    const { result } = renderHook(() => useConversationHistory("conv-123"), {
      wrapper,
    });

    await waitFor(() => {
      expect(result.current.data).toBeDefined();
    });

    // Should call with TIMESTAMP_DESC for bi-directional loading (newest first)
    expect(EventService.searchEventsV1).toHaveBeenCalledWith("conv-123", {
      sort_order: "TIMESTAMP_DESC",
      limit: 100,
    });
    expect(EventService.searchEventsV0).not.toHaveBeenCalled();

    // Should return events and oldest timestamp for WebSocket handoff
    expect(result.current.data?.events).toHaveLength(2);
    expect(result.current.data?.oldestTimestamp).toBe("2026-01-15T10:00:00Z");
  });

  it("returns null oldestTimestamp when no events", async () => {
    const v1SearchEventsSpy = vi.spyOn(EventService, "searchEventsV1");

    vi.mocked(useUserConversation).mockReturnValue({
      data: makeConversation("V1"),
      isLoading: false,
      isPending: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as any);

    v1SearchEventsSpy.mockResolvedValue({
      items: [],
      next_page_id: undefined,
    });

    const { result } = renderHook(() => useConversationHistory("conv-empty"), {
      wrapper,
    });

    await waitFor(() => {
      expect(result.current.data).toBeDefined();
    });

    expect(result.current.data?.events).toHaveLength(0);
    expect(result.current.data?.oldestTimestamp).toBeNull();
  });

  it("calls V0 REST endpoint for V0 conversations", async () => {
    const v0SearchEventsSpy = vi.spyOn(EventService, "searchEventsV0");

    vi.mocked(useUserConversation).mockReturnValue({
      data: makeConversation("V0"),
      isLoading: false,
      isPending: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as any);

    v0SearchEventsSpy.mockResolvedValue([makeEvent()]);

    const { result } = renderHook(() => useConversationHistory("conv-456"), {
      wrapper,
    });

    await waitFor(() => {
      expect(result.current.data).toBeDefined();
    });

    expect(EventService.searchEventsV0).toHaveBeenCalledWith("conv-456");
    expect(EventService.searchEventsV1).not.toHaveBeenCalled();

    // V0 returns events but null oldestTimestamp (no bi-directional loading)
    expect(result.current.data?.events).toHaveLength(1);
    expect(result.current.data?.oldestTimestamp).toBeNull();
  });
});

describe("useConversationHistory cache key stability", () => {
  let localQueryClient: QueryClient;
  let localWrapper: ({
    children,
  }: {
    children: React.ReactNode;
  }) => React.ReactElement;

  beforeEach(() => {
    localQueryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });
    localWrapper = ({ children }: { children: React.ReactNode }) =>
      React.createElement(
        QueryClientProvider,
        { client: localQueryClient },
        children,
      );
  });

  afterEach(() => {
    localQueryClient.clear();
    vi.clearAllMocks();
  });

  it("does not refetch when conversation object changes but version stays the same", async () => {
    const v1Spy = vi.spyOn(EventService, "searchEventsV1");
    v1Spy.mockResolvedValue({ items: [makeEvent()], next_page_id: undefined });

    const conv1 = makeConversation("V1");
    vi.mocked(useUserConversation).mockReturnValue({
      data: conv1,
      isLoading: false,
      isPending: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as any);

    const { result, rerender } = renderHook(
      () => useConversationHistory("conv-stable"),
      { wrapper: localWrapper },
    );

    await waitFor(() => {
      expect(result.current.data).toBeDefined();
    });

    expect(v1Spy).toHaveBeenCalledTimes(1);

    // Simulate background polling: new object reference with different mutable fields
    // but the SAME conversation_version
    const conv2: Conversation = {
      ...conv1,
      last_updated_at: "2099-01-01T00:00:00Z",
      status: "STOPPED",
      runtime_status: "STATUS$STOPPED",
    };
    vi.mocked(useUserConversation).mockReturnValue({
      data: conv2,
      isLoading: false,
      isPending: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as any);

    rerender();

    // Allow any potential async refetch to trigger
    await new Promise((r) => {
      setTimeout(r, 50);
    });

    // Must NOT refetch — version hasn't changed, only mutable fields did
    expect(v1Spy).toHaveBeenCalledTimes(1);
  });

  // Edge case: version change MUST trigger a refetch with the correct endpoint
  it("refetches when conversation_version changes from V0 to V1", async () => {
    const v0Spy = vi.spyOn(EventService, "searchEventsV0");
    const v1Spy = vi.spyOn(EventService, "searchEventsV1");
    v0Spy.mockResolvedValue([makeEvent()]);
    v1Spy.mockResolvedValue({ items: [makeEvent()], next_page_id: undefined });

    // Start with V0
    vi.mocked(useUserConversation).mockReturnValue({
      data: makeConversation("V0"),
      isLoading: false,
      isPending: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as any);

    const { result, rerender } = renderHook(
      () => useConversationHistory("conv-version-change"),
      { wrapper: localWrapper },
    );

    await waitFor(() => {
      expect(result.current.data).toBeDefined();
    });

    expect(v0Spy).toHaveBeenCalledTimes(1);

    // Switch to V1 — new version means new cache key, must refetch
    vi.mocked(useUserConversation).mockReturnValue({
      data: makeConversation("V1"),
      isLoading: false,
      isPending: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as any);

    rerender();

    await waitFor(() => {
      expect(v1Spy).toHaveBeenCalledTimes(1);
    });
  });

  it("treats cached history as never stale (staleTime is Infinity)", async () => {
    const v1Spy = vi.spyOn(EventService, "searchEventsV1");
    v1Spy.mockResolvedValue({ items: [makeEvent()], next_page_id: undefined });

    vi.mocked(useUserConversation).mockReturnValue({
      data: makeConversation("V1"),
      isLoading: false,
      isPending: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as any);

    const { result } = renderHook(
      () => useConversationHistory("conv-stale-check"),
      { wrapper: localWrapper },
    );

    await waitFor(() => {
      expect(result.current.data).toBeDefined();
    });

    // Check the query's staleTime option in the cache
    const queries = localQueryClient.getQueryCache().findAll({
      queryKey: ["conversation-history", "conv-stale-check"],
    });
    expect(queries).toHaveLength(1);
    expect((queries[0].options as Record<string, unknown>).staleTime).toBe(
      Infinity,
    );
  });

  it("has gcTime of at least 30 minutes for navigation resilience", async () => {
    const v1Spy = vi.spyOn(EventService, "searchEventsV1");
    v1Spy.mockResolvedValue({ items: [makeEvent()], next_page_id: undefined });

    vi.mocked(useUserConversation).mockReturnValue({
      data: makeConversation("V1"),
      isLoading: false,
      isPending: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as any);

    const { result } = renderHook(
      () => useConversationHistory("conv-gc-check"),
      { wrapper: localWrapper },
    );

    await waitFor(() => {
      expect(result.current.data).toBeDefined();
    });

    const queries = localQueryClient.getQueryCache().findAll({
      queryKey: ["conversation-history", "conv-gc-check"],
    });
    expect(queries).toHaveLength(1);
    expect(queries[0].options.gcTime).toBeGreaterThanOrEqual(30 * 60 * 1000);
  });
});
