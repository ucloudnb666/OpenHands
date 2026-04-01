import { useQuery } from "@tanstack/react-query";
import { useSelectedOrganizationId } from "#/context/use-selected-organization";
import { useIsOnIntermediatePage } from "#/hooks/use-is-on-intermediate-page";
import { DEFAULT_SETTINGS } from "#/services/settings";
import { Settings, SettingsValue } from "#/types/settings";
import SettingsService from "#/api/settings-service/settings-service.api";
import { useIsAuthed } from "./use-is-authed";
import { useConfig } from "./use-config";
import {
  pickFirstBoolean,
  pickFirstNumber,
  pickFirstString,
  pickNullableString,
} from "#/utils/settings-value-pickers";
import { parseMcpConfig } from "#/utils/mcp-config";

export const getSettingsQueryFn = async (): Promise<Settings> => {
  const settings = await SettingsService.getSettings();
  const agentSettings = (settings.agent_settings ?? {}) as Record<
    string,
    SettingsValue
  >;

  return {
    ...settings,
    llm_model:
      pickFirstString(settings.llm_model, agentSettings["llm.model"]) ??
      DEFAULT_SETTINGS.llm_model,
    llm_base_url:
      pickFirstString(settings.llm_base_url, agentSettings["llm.base_url"]) ??
      DEFAULT_SETTINGS.llm_base_url,
    agent:
      pickFirstString(agentSettings.agent, settings.agent) ??
      DEFAULT_SETTINGS.agent,
    llm_api_key: settings.llm_api_key ?? null,
    confirmation_mode:
      pickFirstBoolean(
        agentSettings["verification.confirmation_mode"],
        settings.confirmation_mode,
      ) ?? DEFAULT_SETTINGS.confirmation_mode,
    security_analyzer:
      pickNullableString(
        agentSettings["verification.security_analyzer"],
        settings.security_analyzer,
      ) ?? DEFAULT_SETTINGS.security_analyzer,
    enable_default_condenser:
      pickFirstBoolean(
        agentSettings["condenser.enabled"],
        settings.enable_default_condenser,
      ) ?? DEFAULT_SETTINGS.enable_default_condenser,
    condenser_max_size:
      pickFirstNumber(
        agentSettings["condenser.max_size"],
        settings.condenser_max_size,
      ) ?? DEFAULT_SETTINGS.condenser_max_size,
    mcp_config: parseMcpConfig(settings.mcp_config ?? agentSettings.mcp_config),
    search_api_key: settings.search_api_key || "",
    email: settings.email || "",
    git_user_name: settings.git_user_name || DEFAULT_SETTINGS.git_user_name,
    git_user_email: settings.git_user_email || DEFAULT_SETTINGS.git_user_email,
    is_new_user: false,
    disabled_skills:
      settings.disabled_skills ?? DEFAULT_SETTINGS.disabled_skills,
    v1_enabled: settings.v1_enabled ?? DEFAULT_SETTINGS.v1_enabled,
    agent_settings_schema: settings.agent_settings_schema ?? null,
    agent_settings: settings.agent_settings ?? DEFAULT_SETTINGS.agent_settings,
    sandbox_grouping_strategy:
      settings.sandbox_grouping_strategy ??
      DEFAULT_SETTINGS.sandbox_grouping_strategy,
  };
};

export const useSettings = () => {
  const isOnIntermediatePage = useIsOnIntermediatePage();
  const { data: userIsAuthenticated } = useIsAuthed();
  const { organizationId } = useSelectedOrganizationId();
  const { data: config } = useConfig();

  const isOss = config?.app_mode === "oss";

  const query = useQuery({
    queryKey: ["settings", organizationId],
    queryFn: getSettingsQueryFn,
    retry: (_, error) => error.status !== 404,
    refetchOnWindowFocus: false,
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 15,
    enabled:
      !isOnIntermediatePage &&
      !!userIsAuthenticated &&
      (isOss || !!organizationId),
    meta: {
      disableToast: true,
    },
  });

  if (query.error?.status === 404) {
    return {
      data: DEFAULT_SETTINGS,
      error: query.error,
      isError: query.isError,
      isLoading: query.isLoading,
      isFetching: query.isFetching,
      isFetched: query.isFetched,
      isSuccess: query.isSuccess,
      status: query.status,
      fetchStatus: query.fetchStatus,
      refetch: query.refetch,
    };
  }

  return query;
};
