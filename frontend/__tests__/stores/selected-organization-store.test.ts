import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { useSelectedOrganizationStore } from "#/stores/selected-organization-store";

describe("useSelectedOrganizationStore", () => {
  afterEach(() => {
    sessionStorage.clear();
  });

  it("should have null as initial organizationId", () => {
    const { result } = renderHook(() => useSelectedOrganizationStore());
    expect(result.current.organizationId).toBeNull();
  });

  it("should update organizationId when setOrganizationId is called", () => {
    const { result } = renderHook(() => useSelectedOrganizationStore());

    act(() => {
      result.current.setOrganizationId("org-123");
    });

    expect(result.current.organizationId).toBe("org-123");
  });

  it("should allow setting organizationId to null", () => {
    const { result } = renderHook(() => useSelectedOrganizationStore());

    act(() => {
      result.current.setOrganizationId("org-123");
    });

    expect(result.current.organizationId).toBe("org-123");

    act(() => {
      result.current.setOrganizationId(null);
    });

    expect(result.current.organizationId).toBeNull();
  });

  it("should share state across multiple hook instances", () => {
    const { result: result1 } = renderHook(() =>
      useSelectedOrganizationStore(),
    );
    const { result: result2 } = renderHook(() =>
      useSelectedOrganizationStore(),
    );

    act(() => {
      result1.current.setOrganizationId("shared-organization");
    });

    expect(result2.current.organizationId).toBe("shared-organization");
  });

  it("should persist organizationId to sessionStorage when set", () => {
    const { result } = renderHook(() => useSelectedOrganizationStore());

    act(() => {
      result.current.setOrganizationId("org-456");
    });

    expect(sessionStorage.getItem("selectedOrgId")).toBe("org-456");
  });

  it("should remove organizationId from sessionStorage when set to null", () => {
    const { result } = renderHook(() => useSelectedOrganizationStore());

    act(() => {
      result.current.setOrganizationId("org-789");
    });

    act(() => {
      result.current.setOrganizationId(null);
    });

    expect(sessionStorage.getItem("selectedOrgId")).toBeNull();
  });
});
