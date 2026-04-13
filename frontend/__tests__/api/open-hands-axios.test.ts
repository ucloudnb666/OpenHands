import { afterEach, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "#/mocks/node";
import { openHands } from "#/api/open-hands-axios";
import { useSelectedOrganizationStore } from "#/stores/selected-organization-store";

describe("openHands axios instance", () => {
  afterEach(() => {
    sessionStorage.clear();
  });

  it("should attach X-Org-Id header when an organization is selected", async () => {
    // Arrange
    let capturedOrgHeader: string | null = null;
    server.use(
      http.get("*/api/test-endpoint", ({ request }) => {
        capturedOrgHeader = request.headers.get("X-Org-Id");
        return HttpResponse.json({ ok: true });
      }),
    );
    useSelectedOrganizationStore.setState({ organizationId: "org-abc-123" });

    // Act
    await openHands.get("/api/test-endpoint");

    // Assert
    expect(capturedOrgHeader).toBe("org-abc-123");
  });

  it("should not attach X-Org-Id header when no organization is selected", async () => {
    // Arrange
    let capturedOrgHeader: string | null = "should-be-replaced";
    server.use(
      http.get("*/api/test-endpoint", ({ request }) => {
        capturedOrgHeader = request.headers.get("X-Org-Id");
        return HttpResponse.json({ ok: true });
      }),
    );

    // Act
    await openHands.get("/api/test-endpoint");

    // Assert
    expect(capturedOrgHeader).toBeNull();
  });
});
