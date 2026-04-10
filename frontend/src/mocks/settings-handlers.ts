import { http, delay, HttpResponse } from "msw";
import { WebClientConfig } from "#/api/option-service/option.types";
import { DEFAULT_SETTINGS } from "#/services/settings";
import { Provider, Settings, SettingsValue } from "#/types/settings";

const DEFAULT_AGENT_SETTINGS = DEFAULT_SETTINGS.agent_settings ?? {};
const DEFAULT_MODEL =
  typeof DEFAULT_AGENT_SETTINGS["llm.model"] === "string"
    ? DEFAULT_AGENT_SETTINGS["llm.model"]
    : "openhands/claude-opus-4-5-20251101";

export const createMockWebClientConfig = (
  overrides: Partial<WebClientConfig> = {},
): WebClientConfig => ({
  app_mode: "oss",
  posthog_client_key: "test-posthog-key",
  feature_flags: {
    enable_billing: false,
    hide_llm_settings: false,
    enable_jira: false,
    enable_jira_dc: false,
    enable_linear: false,
    hide_users_page: false,
    hide_billing_page: false,
    hide_integrations_page: false,
    ...overrides.feature_flags,
  },
  providers_configured: [],
  maintenance_start_time: null,
  auth_url: null,
  recaptcha_site_key: null,
  faulty_models: [],
  error_message: null,
  updated_at: new Date().toISOString(),
  github_app_slug: null,
  ...overrides,
});

const MOCK_AGENT_SETTINGS_SCHEMA: NonNullable<
  Settings["agent_settings_schema"]
> = {
  model_name: "AgentSettings",
  sections: [
    {
      key: "llm",
      label: "LLM",
      fields: [
        {
          key: "llm.model",
          label: "Model",
          section: "llm",
          section_label: "LLM",
          value_type: "string",
          default: DEFAULT_MODEL,
          choices: [],
          depends_on: [],
          prominence: "critical",
          secret: false,
          required: true,
        },
        {
          key: "llm.api_key",
          label: "API Key",
          section: "llm",
          section_label: "LLM",
          value_type: "string",
          default: null,
          choices: [],
          depends_on: [],
          prominence: "critical",
          secret: true,
          required: false,
        },
        {
          key: "llm.base_url",
          label: "Base URL",
          section: "llm",
          section_label: "LLM",
          value_type: "string",
          default: null,
          choices: [],
          depends_on: [],
          prominence: "critical",
          secret: false,
          required: false,
        },
      ],
    },
    {
      key: "critic",
      label: "Critic",
      fields: [
        {
          key: "critic.enabled",
          label: "Enable critic",
          section: "critic",
          section_label: "Critic",
          value_type: "boolean",
          default: false,
          choices: [],
          depends_on: [],
          prominence: "critical",
          secret: false,
          required: true,
        },
        {
          key: "critic.mode",
          label: "Mode",
          section: "critic",
          section_label: "Critic",
          value_type: "string",
          default: "finish_and_message",
          choices: [
            { label: "finish_and_message", value: "finish_and_message" },
            { label: "all_actions", value: "all_actions" },
          ],
          depends_on: ["critic.enabled"],
          prominence: "minor",
          secret: false,
          required: true,
        },
      ],
    },
  ],
};

const MOCK_CONVERSATION_SETTINGS_SCHEMA: NonNullable<
  Settings["conversation_settings_schema"]
> = {
  model_name: "ConversationSettings",
  sections: [
    {
      key: "general",
      label: "General",
      fields: [
        {
          key: "max_iterations",
          label: "Max iterations",
          section: "general",
          section_label: "General",
          value_type: "integer",
          default: 500,
          choices: [],
          depends_on: [],
          prominence: "major",
          secret: false,
          required: true,
        },
      ],
    },
    {
      key: "verification",
      label: "Verification",
      fields: [
        {
          key: "confirmation_mode",
          label: "Confirmation mode",
          section: "verification",
          section_label: "Verification",
          value_type: "boolean",
          default: false,
          choices: [],
          depends_on: [],
          prominence: "major",
          secret: false,
          required: true,
        },
        {
          key: "security_analyzer",
          label: "Security analyzer",
          section: "verification",
          section_label: "Verification",
          value_type: "string",
          default: "llm",
          choices: [
            { label: "llm", value: "llm" },
            { label: "none", value: "none" },
          ],
          depends_on: ["confirmation_mode"],
          prominence: "major",
          secret: false,
          required: false,
        },
      ],
    },
  ],
};

export const MOCK_DEFAULT_USER_SETTINGS: Settings = {
  ...DEFAULT_SETTINGS,
  provider_tokens_set: {},
  agent_settings_schema: MOCK_AGENT_SETTINGS_SCHEMA,
  agent_settings: {
    ...DEFAULT_AGENT_SETTINGS,
    "critic.mode": "finish_and_message",
    "critic.enabled": false,
    "llm.api_key": null,
    "llm.model": DEFAULT_MODEL,
  },
  conversation_settings_schema: MOCK_CONVERSATION_SETTINGS_SCHEMA,
  conversation_settings: {
    ...(DEFAULT_SETTINGS.conversation_settings ?? {}),
  },
};

const MOCK_USER_PREFERENCES: {
  settings: Settings | null;
} = {
  settings: null,
};

export const resetTestHandlersMockSettings = () => {
  MOCK_USER_PREFERENCES.settings = structuredClone(MOCK_DEFAULT_USER_SETTINGS);
};

export const SETTINGS_HANDLERS = [
  http.get("/api/options/models", async () =>
    HttpResponse.json({
      models: [
        "anthropic/claude-3.5",
        "anthropic/claude-sonnet-4-20250514",
        "anthropic/claude-sonnet-4-5-20250929",
        "anthropic/claude-haiku-4-5-20251001",
        "anthropic/claude-opus-4-5-20251101",
        "openai/gpt-3.5-turbo",
        "openai/gpt-4o",
        "openai/gpt-4o-mini",
        "openhands/claude-sonnet-4-20250514",
        "openhands/claude-sonnet-4-5-20250929",
        "openhands/claude-haiku-4-5-20251001",
        "openhands/claude-opus-4-5-20251101",
        "sambanova/Meta-Llama-3.1-8B-Instruct",
      ],
      verified_models: [
        "claude-opus-4-5-20251101",
        "claude-sonnet-4-5-20250929",
      ],
      verified_providers: [
        "openhands",
        "anthropic",
        "openai",
        "mistral",
        "gemini",
        "deepseek",
        "moonshot",
        "minimax",
      ],
      default_model: "openhands/claude-opus-4-5-20251101",
    }),
  ),

  http.get("/api/options/agents", async () =>
    HttpResponse.json(["CodeActAgent", "CoActAgent"]),
  ),

  http.get("/api/options/security-analyzers", async () =>
    HttpResponse.json(["llm", "none"]),
  ),

  http.get("/api/v1/web-client/config", () => {
    const mockSaas = import.meta.env.VITE_MOCK_SAAS === "true";

    const config: WebClientConfig = {
      app_mode: mockSaas ? "saas" : "oss",
      posthog_client_key: "fake-posthog-client-key",
      feature_flags: {
        enable_billing: mockSaas,
        hide_llm_settings: false,
        enable_jira: false,
        enable_jira_dc: false,
        enable_linear: false,
        hide_users_page: false,
        hide_billing_page: false,
        hide_integrations_page: false,
      },
      providers_configured: [],
      maintenance_start_time: null,
      auth_url: null,
      recaptcha_site_key: null,
      faulty_models: [],
      error_message: null,
      updated_at: new Date().toISOString(),
      github_app_slug: mockSaas ? "openhands" : null,
    };

    return HttpResponse.json(config);
  }),

  http.get("/api/settings/conversation-schema", async () => {
    await delay();
    return HttpResponse.json(MOCK_CONVERSATION_SETTINGS_SCHEMA);
  }),

  http.get("/api/settings", async () => {
    await delay();
    const { settings } = MOCK_USER_PREFERENCES;

    if (!settings) return HttpResponse.json(null, { status: 404 });

    return HttpResponse.json(settings);
  }),

  http.get("/api/settings/agent-schema", async () => {
    await delay();
    return HttpResponse.json(MOCK_AGENT_SETTINGS_SCHEMA);
  }),

  http.post("/api/settings", async ({ request }) => {
    await delay();
    const body = (await request.json()) as Record<string, unknown> | null;

    if (body) {
      const current =
        MOCK_USER_PREFERENCES.settings ||
        structuredClone(MOCK_DEFAULT_USER_SETTINGS);
      const agentFieldKeys = new Set(
        current.agent_settings_schema?.sections.flatMap((section) =>
          section.fields.map((field) => field.key),
        ) ?? [],
      );
      const conversationFieldKeys = new Set(
        current.conversation_settings_schema?.sections.flatMap((section) =>
          section.fields.map((field) => field.key),
        ) ?? [],
      );
      const agentSettings = {
        ...(current.agent_settings ?? {}),
      } as Record<string, SettingsValue>;
      const conversationSettings = {
        ...(current.conversation_settings ?? {}),
      } as Record<string, SettingsValue>;

      const nextSettings: Settings = {
        ...current,
        ...(body as Partial<Settings>),
      };

      for (const [key, value] of Object.entries(body)) {
        if (agentFieldKeys.has(key)) {
          agentSettings[key] =
            value === null ||
            typeof value === "boolean" ||
            typeof value === "number" ||
            typeof value === "string" ||
            Array.isArray(value) ||
            (typeof value === "object" && value !== null)
              ? (value as SettingsValue)
              : null;
        }
        if (conversationFieldKeys.has(key)) {
          conversationSettings[key] =
            value === null ||
            typeof value === "boolean" ||
            typeof value === "number" ||
            typeof value === "string" ||
            Array.isArray(value) ||
            (typeof value === "object" && value !== null)
              ? (value as SettingsValue)
              : null;
        }
      }

      const nestedConversationSettings = body.conversation_settings;
      if (
        nestedConversationSettings &&
        typeof nestedConversationSettings === "object" &&
        !Array.isArray(nestedConversationSettings)
      ) {
        for (const [key, value] of Object.entries(nestedConversationSettings)) {
          if (conversationFieldKeys.has(key)) {
            conversationSettings[key] =
              value === null ||
              typeof value === "boolean" ||
              typeof value === "number" ||
              typeof value === "string" ||
              Array.isArray(value) ||
              (typeof value === "object" && value !== null)
                ? (value as SettingsValue)
                : null;
          }
        }
      }

      nextSettings.agent_settings = agentSettings;
      nextSettings.conversation_settings = conversationSettings;
      MOCK_USER_PREFERENCES.settings = nextSettings;

      return HttpResponse.json(null, { status: 200 });
    }

    return HttpResponse.json(null, { status: 400 });
  }),

  http.post("/api/add-git-providers", async ({ request }) => {
    const body = await request.json();

    if (typeof body === "object" && body?.provider_tokens) {
      const rawTokens = body.provider_tokens as Record<
        string,
        { token?: string }
      >;

      const providerTokensSet: Partial<Record<Provider, string | null>> =
        Object.fromEntries(
          Object.entries(rawTokens)
            .filter(([, val]) => val?.token)
            .map(([provider]) => [provider as Provider, ""]),
        );

      MOCK_USER_PREFERENCES.settings = {
        ...(MOCK_USER_PREFERENCES.settings || MOCK_DEFAULT_USER_SETTINGS),
        provider_tokens_set: providerTokensSet,
      };

      return HttpResponse.json(true, { status: 200 });
    }

    return HttpResponse.json(null, { status: 400 });
  }),
];
