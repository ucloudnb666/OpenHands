import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { openHands } from "#/api/open-hands-axios";
import { useSubmitEnterpriseLead } from "#/hooks/mutation/use-submit-enterprise-lead";

vi.mock("#/api/open-hands-axios");

describe("useSubmitEnterpriseLead", () => {
  const mockFormData = {
    requestType: "saas" as const,
    name: "John Doe",
    company: "Acme Corp",
    email: "john@acme.com",
    message: "Interested in enterprise plan.",
  };

  const mockResponse = {
    id: "test-submission-id",
    status: "pending",
    created_at: "2025-03-19T00:00:00Z",
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("should call API with correct payload", async () => {
    vi.mocked(openHands.post).mockResolvedValue({ data: mockResponse });

    const { result } = renderHook(() => useSubmitEnterpriseLead(), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={new QueryClient()}>
          {children}
        </QueryClientProvider>
      ),
    });

    result.current.mutate(mockFormData);

    await waitFor(() => {
      expect(openHands.post).toHaveBeenCalledWith(
        "/api/forms/submit",
        {
          form_type: "enterprise_lead",
          answers: {
            request_type: "saas",
            name: "John Doe",
            company: "Acme Corp",
            email: "john@acme.com",
            message: "Interested in enterprise plan.",
          },
        },
        { withCredentials: true },
      );
    });
  });

  it("should return success state after successful submission", async () => {
    vi.mocked(openHands.post).mockResolvedValue({ data: mockResponse });

    const { result } = renderHook(() => useSubmitEnterpriseLead(), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={new QueryClient()}>
          {children}
        </QueryClientProvider>
      ),
    });

    result.current.mutate(mockFormData);

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
      expect(result.current.data).toEqual(mockResponse);
    });
  });

  it("should return error state after failed submission", async () => {
    const mockError = new Error("Network error");
    vi.mocked(openHands.post).mockRejectedValue(mockError);

    const { result } = renderHook(() => useSubmitEnterpriseLead(), {
      wrapper: ({ children }) => (
        <QueryClientProvider
          client={
            new QueryClient({
              defaultOptions: {
                mutations: {
                  retry: false,
                },
              },
            })
          }
        >
          {children}
        </QueryClientProvider>
      ),
    });

    result.current.mutate(mockFormData);

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
      expect(result.current.error).toBe(mockError);
    });
  });

  it("should handle self-hosted request type", async () => {
    vi.mocked(openHands.post).mockResolvedValue({ data: mockResponse });

    const selfHostedFormData = {
      ...mockFormData,
      requestType: "self-hosted" as const,
    };

    const { result } = renderHook(() => useSubmitEnterpriseLead(), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={new QueryClient()}>
          {children}
        </QueryClientProvider>
      ),
    });

    result.current.mutate(selfHostedFormData);

    await waitFor(() => {
      expect(openHands.post).toHaveBeenCalledWith(
        "/api/forms/submit",
        expect.objectContaining({
          answers: expect.objectContaining({
            request_type: "self-hosted",
          }),
        }),
        { withCredentials: true },
      );
    });
  });

  it("should be in pending state while submitting", async () => {
    let resolvePromise: (value: { data: typeof mockResponse }) => void;
    const controlledPromise = new Promise<{ data: typeof mockResponse }>(
      (resolve) => {
        resolvePromise = resolve;
      },
    );

    vi.mocked(openHands.post).mockReturnValue(controlledPromise);

    const { result } = renderHook(() => useSubmitEnterpriseLead(), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={new QueryClient()}>
          {children}
        </QueryClientProvider>
      ),
    });

    result.current.mutate(mockFormData);

    await waitFor(() => {
      expect(result.current.isPending).toBe(true);
    });

    resolvePromise!({ data: mockResponse });

    await waitFor(() => {
      expect(result.current.isPending).toBe(false);
      expect(result.current.isSuccess).toBe(true);
    });
  });
});
