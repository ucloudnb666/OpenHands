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
    useRevalidator: () => ({
      revalidate: vi.fn(),
    }),
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
    sdk_settings_values: {
      ...MOCK_DEFAULT_USER_SETTINGS.sdk_settings_values,
      ...overrides.sdk_settings_values,
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
    llm_api_key_for_byor: null,
    llm_base_url: "",
    ...overrides,
  };
}

function renderLlmSettingsScreen(
  options: {
    appMode?: "oss" | "saas";
    organizationId?: string;
    meData?: OrganizationMember;
  } = {},
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
  const organizationId = options.organizationId ?? "1";
  const appMode = options.appMode ?? "oss";

  useSelectedOrganizationStore.setState({ organizationId });
  mockUseConfig.mockReturnValue({
    data: { app_mode: appMode },
    isLoading: false,
  });

  if (appMode === "saas") {
    queryClient.setQueryData(
      ["organizations", organizationId, "me"],
      options.meData ?? buildOrganizationMember({ org_id: organizationId }),
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

  mockUseSearchParams.mockReturnValue([
    {
      get: () => null,
    },
    vi.fn(),
  ]);
  mockUseIsAuthed.mockReturnValue({ data: true, isLoading: false });
  mockUseConfig.mockReturnValue({
    data: { app_mode: "oss" },
    isLoading: false,
  });
  useSelectedOrganizationStore.setState({ organizationId: "1" });
});

describe("LlmSettingsScreen", () => {
  it("renders schema-driven basic fields from sdk_settings_schema", async () => {
    vi.spyOn(SettingsService, "getSettings").mockResolvedValue(buildSettings());

    renderLlmSettingsScreen();

    await screen.findByTestId("llm-settings-screen");
    expect(screen.getByTestId("sdk-settings-llm.model")).toBeInTheDocument();
    expect(screen.getByTestId("sdk-settings-llm.api_key")).toBeInTheDocument();
    expect(screen.getByTestId("sdk-settings-critic.enabled")).toBeInTheDocument();
    expect(
      screen.queryByTestId("sdk-settings-critic.mode"),
    ).not.toBeInTheDocument();
  });

  it("reveals dependent advanced fields when their controlling value is enabled", async () => {
    vi.spyOn(SettingsService, "getSettings").mockResolvedValue(buildSettings());

    renderLlmSettingsScreen();

    await screen.findByTestId("llm-settings-screen");
    await userEvent.click(screen.getByTestId("llm-settings-advanced-toggle"));

    const criticSwitch = screen.getByTestId("sdk-settings-critic.enabled");
    expect(criticSwitch).toBeInTheDocument();
    expect(
      screen.queryByTestId("sdk-settings-critic.mode"),
    ).not.toBeInTheDocument();

    await userEvent.click(criticSwitch);

    expect(screen.getByTestId("sdk-settings-critic.mode")).toBeInTheDocument();
  });

  it("starts in advanced mode when advanced sdk values override defaults", async () => {
    vi.spyOn(SettingsService, "getSettings").mockResolvedValue(
      buildSettings({
        sdk_settings_values: {
          ...MOCK_DEFAULT_USER_SETTINGS.sdk_settings_values,
          "critic.mode": "all_actions",
          "critic.enabled": true,
        },
      }),
    );

    renderLlmSettingsScreen();

    await screen.findByTestId("llm-settings-screen");
    expect(screen.getByTestId("sdk-settings-critic.mode")).toBeInTheDocument();
  });

  it("saves changed schema-driven fields through the generic settings payload", async () => {
    vi.spyOn(SettingsService, "getSettings").mockResolvedValue(buildSettings());
    const saveSettingsSpy = vi
      .spyOn(SettingsService, "saveSettings")
      .mockResolvedValue(true);

    renderLlmSettingsScreen();

    const llmModelInput = await screen.findByTestId("sdk-settings-llm.model");
    await userEvent.clear(llmModelInput);
    await userEvent.type(llmModelInput, "openai/gpt-4o-mini");
    await userEvent.click(screen.getByTestId("save-button"));

    await waitFor(() => {
      expect(saveSettingsSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          "llm.model": "openai/gpt-4o-mini",
        }),
      );
    });
  });

  it("hides the save button for read-only SaaS members", async () => {
    vi.spyOn(SettingsService, "getSettings").mockResolvedValue(buildSettings());

    renderLlmSettingsScreen({
      appMode: "saas",
      organizationId: "2",
      meData: buildOrganizationMember({ org_id: "2", role: "member" }),
    });

    await screen.findByTestId("llm-settings-screen");
    expect(screen.queryByTestId("save-button")).not.toBeInTheDocument();
    expect(screen.getByTestId("sdk-settings-llm.model")).toBeDisabled();
  });

  it("shows a fallback message when sdk settings schema is unavailable", async () => {
    vi.spyOn(SettingsService, "getSettings").mockResolvedValue(
      buildSettings({ sdk_settings_schema: null }),
    );

    renderLlmSettingsScreen();

    expect(
      await screen.findByText("SETTINGS$SDK_SCHEMA_UNAVAILABLE"),
    ).toBeInTheDocument();
  });
});
