import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsService from "#/api/settings-service/settings-service.api";
import {
  MOCK_DEFAULT_USER_SETTINGS,
  resetTestHandlersMockSettings,
} from "#/mocks/handlers";
import LlmSettingsScreen from "#/routes/llm-settings";
import { useSelectedOrganizationStore } from "#/stores/selected-organization-store";
import { OrganizationMember } from "#/types/org";
import { Settings } from "#/types/settings";

const mockUseSearchParams = vi.fn();
vi.mock("react-router", async () => {
  const actual =
    await vi.importActual<typeof import("react-router")>("react-router");
  return {
    ...actual,
    useSearchParams: () => mockUseSearchParams(),
    useRevalidator: () => ({ revalidate: vi.fn() }),
  };
});

const mockUseIsAuthed = vi.fn();
vi.mock("#/hooks/query/use-is-authed", () => ({
  useIsAuthed: () => mockUseIsAuthed(),
}));

const mockUseConfig = vi.fn();
vi.mock("#/hooks/query/use-config", () => ({
  useConfig: () => mockUseConfig(),
}));

function buildSettings(overrides: Partial<Settings> = {}): Settings {
  return {
    ...MOCK_DEFAULT_USER_SETTINGS,
    ...overrides,
    agent_settings: {
      ...MOCK_DEFAULT_USER_SETTINGS.agent_settings,
      ...overrides.agent_settings,
    },
  };
}

function buildOrganizationMember(
  overrides: Partial<OrganizationMember> = {},
): OrganizationMember {
  return {
    org_id: "1",
    user_id: "99",
    email: "owner@example.com",
    role: "owner",
    status: "active",
    llm_api_key: "",
    max_iterations: 20,
    llm_model: "",
    llm_base_url: "",
    ...overrides,
  };
}

function renderLlmSettingsScreen({
  appMode = "oss",
  organizationId = "1",
  meData,
}: {
  appMode?: "oss" | "saas";
  organizationId?: string;
  meData?: OrganizationMember;
} = {}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  useSelectedOrganizationStore.setState({ organizationId });
  mockUseConfig.mockReturnValue({
    data: { app_mode: appMode },
    isLoading: false,
  });

  if (appMode === "saas") {
    queryClient.setQueryData(
      ["organizations", organizationId, "me"],
      meData ?? buildOrganizationMember({ org_id: organizationId }),
    );
  }

  return render(<LlmSettingsScreen />, {
    wrapper: ({ children }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
  });
}

beforeEach(() => {
  vi.restoreAllMocks();
  resetTestHandlersMockSettings();
  mockUseSearchParams.mockReturnValue([{ get: () => null }, vi.fn()]);
  mockUseIsAuthed.mockReturnValue({ data: true, isLoading: false });
  mockUseConfig.mockReturnValue({
    data: { app_mode: "oss" },
    isLoading: false,
  });
  useSelectedOrganizationStore.setState({ organizationId: "1" });
});

describe("LlmSettingsScreen", () => {
  it("renders the basic LLM form in OSS mode", async () => {
    vi.spyOn(SettingsService, "getSettings").mockResolvedValue(buildSettings());

    renderLlmSettingsScreen({ appMode: "oss" });

    await screen.findByTestId("llm-settings-screen");
    expect(screen.getByTestId("llm-settings-form-basic")).toBeInTheDocument();
    expect(screen.getByTestId("llm-provider-input")).toBeInTheDocument();
    expect(screen.getByTestId("llm-model-input")).toBeInTheDocument();
    expect(screen.getByTestId("llm-api-key-input")).toBeInTheDocument();
    expect(screen.getByTestId("submit-button")).toBeInTheDocument();
  });

  it("auto-opens advanced mode when advanced LLM settings are already set", async () => {
    vi.spyOn(SettingsService, "getSettings").mockResolvedValue(
      buildSettings({
        llm_model: "openai/gpt-4o",
        agent_settings: {
          "llm.base_url": "https://api.openai.com/v1",
          agent: "CoActAgent",
        },
      }),
    );

    renderLlmSettingsScreen({ appMode: "oss" });

    await screen.findByTestId("llm-settings-form-advanced");
    expect(screen.getByTestId("llm-custom-model-input")).toBeInTheDocument();
    expect(screen.getByTestId("base-url-input")).toBeInTheDocument();
  });

  it("hides the API key input for OpenHands provider in SaaS mode", async () => {
    vi.spyOn(SettingsService, "getSettings").mockResolvedValue(buildSettings());

    renderLlmSettingsScreen({ appMode: "saas" });

    await screen.findByTestId("llm-settings-screen");
    expect(screen.queryByTestId("llm-api-key-input")).not.toBeInTheDocument();
    expect(screen.getByTestId("openhands-api-key-help")).toBeInTheDocument();
  });

  it("shows the API key input for non-OpenHands providers in SaaS mode", async () => {
    vi.spyOn(SettingsService, "getSettings").mockResolvedValue(
      buildSettings({ llm_model: "openai/gpt-4o" }),
    );

    renderLlmSettingsScreen({ appMode: "saas" });

    await screen.findByTestId("llm-settings-screen");
    expect(screen.getByTestId("llm-api-key-input")).toBeInTheDocument();
  });

  it("makes team members read-only in SaaS mode", async () => {
    vi.spyOn(SettingsService, "getSettings").mockResolvedValue(buildSettings());

    renderLlmSettingsScreen({
      appMode: "saas",
      meData: buildOrganizationMember({ role: "member" }),
    });

    await screen.findByTestId("llm-settings-screen");
    expect(screen.getByTestId("advanced-settings-switch")).toBeDisabled();
    expect(screen.queryByTestId("submit-button")).not.toBeInTheDocument();
  });

  it("submits basic form values through SDK setting keys", async () => {
    vi.spyOn(SettingsService, "getSettings").mockResolvedValue(
      buildSettings({ llm_model: "openai/gpt-4o" }),
    );
    const saveSettingsSpy = vi
      .spyOn(SettingsService, "saveSettings")
      .mockResolvedValue(true);

    renderLlmSettingsScreen({ appMode: "oss" });

    const apiKeyInput = await screen.findByTestId("llm-api-key-input");
    await userEvent.type(apiKeyInput, "test-api-key");
    await userEvent.click(screen.getByTestId("submit-button"));

    await waitFor(() => {
      expect(saveSettingsSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          "llm.model": "openai/gpt-4o",
          "llm.api_key": "test-api-key",
          "llm.base_url": "",
        }),
      );
    });
  });

  it("submits advanced form values through SDK setting keys", async () => {
    vi.spyOn(SettingsService, "getSettings").mockResolvedValue(
      buildSettings({
        llm_model: "openai/gpt-4o",
        agent_settings: {
          "llm.base_url": "https://api.openai.com/v1",
          agent: "CoActAgent",
        },
      }),
    );
    const saveSettingsSpy = vi
      .spyOn(SettingsService, "saveSettings")
      .mockResolvedValue(true);

    renderLlmSettingsScreen({ appMode: "oss" });

    const modelInput = await screen.findByTestId("llm-custom-model-input");
    await userEvent.clear(modelInput);
    await userEvent.type(modelInput, "anthropic/claude-sonnet-4");
    await userEvent.click(screen.getByTestId("submit-button"));

    await waitFor(() => {
      expect(saveSettingsSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          "llm.model": "anthropic/claude-sonnet-4",
          "llm.base_url": "https://api.openai.com/v1",
        }),
      );
    });
  });
});
