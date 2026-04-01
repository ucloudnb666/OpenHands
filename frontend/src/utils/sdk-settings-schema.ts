import {
  SettingProminence,
  Settings,
  SettingsFieldSchema,
  SettingsSchema,
  SettingsSectionSchema,
  SettingsValue,
} from "#/types/settings";

export type SettingsFormValues = Record<string, string | boolean>;
export type SettingsDirtyState = Record<string, boolean>;
export type SdkSettingsPayload = Record<string, SettingsValue>;

export type SettingsView = "basic" | "advanced" | "all";

/** Fields that are rendered by purpose-built components instead of the
 *  generic `SchemaField` renderer. */
export const SPECIALLY_RENDERED_KEYS = new Set([
  "llm.model",
  "llm.api_key",
  "llm.base_url",
]);

/** Prominence tiers visible at each view level. */
const VIEW_PROMINENCES: Record<SettingsView, Set<SettingProminence>> = {
  basic: new Set<SettingProminence>(["critical"]),
  advanced: new Set<SettingProminence>(["critical", "major"]),
  all: new Set<SettingProminence>(["critical", "major", "minor"]),
};

function getSchemaFields(schema: SettingsSchema): SettingsFieldSchema[] {
  return schema.sections.flatMap((section) => section.fields);
}

export function getAgentSettingValue(
  settings: Settings,
  key: string,
): SettingsValue {
  return settings.agent_settings?.[key] ?? null;
}

function isChoiceField(field: SettingsFieldSchema): boolean {
  return field.choices.length > 0;
}

function isCriticalField(field: SettingsFieldSchema): boolean {
  return field.prominence === "critical";
}

function isMinorField(field: SettingsFieldSchema): boolean {
  return field.prominence === "minor";
}

function normalizeFieldValue(
  field: SettingsFieldSchema,
  rawValue: unknown,
): string | boolean {
  const resolvedValue = rawValue ?? field.default;

  if (isChoiceField(field)) {
    return resolvedValue === null || resolvedValue === undefined
      ? ""
      : String(resolvedValue);
  }

  if (field.value_type === "boolean") {
    return Boolean(resolvedValue ?? false);
  }

  if (resolvedValue === null || resolvedValue === undefined) {
    return "";
  }

  if (field.value_type === "array" || field.value_type === "object") {
    return JSON.stringify(resolvedValue, null, 2);
  }

  return String(resolvedValue);
}

function normalizeComparableValue(
  field: SettingsFieldSchema,
  rawValue: unknown,
): boolean | number | string | null {
  if (rawValue === undefined) {
    return null;
  }

  if (field.value_type === "boolean") {
    if (typeof rawValue === "string") {
      if (rawValue === "true") {
        return true;
      }
      if (rawValue === "false") {
        return false;
      }
    }
    if (rawValue === null) {
      return null;
    }
    return Boolean(rawValue);
  }

  if (field.value_type === "integer" || field.value_type === "number") {
    if (rawValue === "" || rawValue === null) {
      return null;
    }

    const parsedValue =
      typeof rawValue === "number" ? rawValue : Number(String(rawValue));
    return Number.isNaN(parsedValue) ? null : parsedValue;
  }

  if (field.value_type === "array" || field.value_type === "object") {
    if (rawValue === null) {
      return null;
    }

    if (typeof rawValue === "string") {
      const trimmedValue = rawValue.trim();
      if (!trimmedValue) {
        return null;
      }
      try {
        return JSON.stringify(JSON.parse(trimmedValue));
      } catch {
        return trimmedValue;
      }
    }

    return JSON.stringify(rawValue);
  }

  if (rawValue === null) {
    return null;
  }

  return String(rawValue);
}

export function buildInitialSettingsFormValues(
  settings: Settings,
  schemaOverride?: SettingsSchema | null,
): SettingsFormValues {
  const schema = schemaOverride ?? settings.agent_settings_schema;
  if (!schema) {
    return {};
  }

  return Object.fromEntries(
    getSchemaFields(schema).map((field) => [
      field.key,
      normalizeFieldValue(field, getAgentSettingValue(settings, field.key)),
    ]),
  );
}

/** Determine which view tier to default to based on whether the user has
 *  overridden any non-critical settings. */
export function inferInitialView(
  settings: Settings,
  schemaOverride?: SettingsSchema | null,
): SettingsView {
  const schema = schemaOverride ?? settings.agent_settings_schema;
  if (!schema) {
    return "basic";
  }

  let hasMinorOverride = false;
  let hasMajorOverride = false;

  for (const field of getSchemaFields(schema)) {
    if (!isCriticalField(field)) {
      const currentValue = getAgentSettingValue(settings, field.key);
      const isDifferent =
        normalizeComparableValue(
          field,
          currentValue ?? field.default ?? null,
        ) !== normalizeComparableValue(field, field.default ?? null);

      if (isDifferent) {
        if (isMinorField(field)) {
          hasMinorOverride = true;
        } else {
          hasMajorOverride = true;
        }
      }
    }
  }

  if (hasMinorOverride) return "all";
  if (hasMajorOverride) return "advanced";
  return "basic";
}

/** @deprecated Use {@link inferInitialView} instead. */
export function hasAdvancedSettingsOverrides(settings: Settings): boolean {
  return inferInitialView(settings) !== "basic";
}

export function isSettingsFieldVisible(
  field: SettingsFieldSchema,
  values: SettingsFormValues,
): boolean {
  return field.depends_on.every((dependency) => values[dependency] === true);
}

function parseBooleanFieldValue(rawValue: string | boolean): boolean | null {
  if (typeof rawValue === "boolean") {
    return rawValue;
  }

  const normalizedValue = rawValue.trim().toLowerCase();
  if (!normalizedValue) {
    return null;
  }
  if (normalizedValue === "true") {
    return true;
  }
  if (normalizedValue === "false") {
    return false;
  }

  throw new Error(`Expected a boolean value, received: ${rawValue}`);
}

function coerceFieldValue(
  field: SettingsFieldSchema,
  rawValue: string | boolean,
): SettingsValue {
  if (field.value_type === "boolean") {
    return parseBooleanFieldValue(rawValue);
  }

  if (field.value_type === "integer" || field.value_type === "number") {
    const stringValue = String(rawValue).trim();
    if (!stringValue) {
      return null;
    }

    const parsedValue = Number(stringValue);
    if (Number.isNaN(parsedValue)) {
      throw new Error(`Expected a numeric value, received: ${stringValue}`);
    }
    if (field.value_type === "integer" && !Number.isInteger(parsedValue)) {
      throw new Error(`Expected an integer value, received: ${stringValue}`);
    }

    return parsedValue;
  }

  if (field.value_type === "array" || field.value_type === "object") {
    const stringValue = String(rawValue).trim();
    if (!stringValue) {
      return null;
    }

    let parsedValue: unknown;
    try {
      parsedValue = JSON.parse(stringValue);
    } catch {
      throw new Error(`Invalid JSON for ${field.label}`);
    }

    if (field.value_type === "array") {
      if (!Array.isArray(parsedValue)) {
        throw new Error(`${field.label} must be a JSON array`);
      }
      return parsedValue as SettingsValue[];
    }

    if (
      parsedValue === null ||
      Array.isArray(parsedValue) ||
      typeof parsedValue !== "object"
    ) {
      throw new Error(`${field.label} must be a JSON object`);
    }

    return parsedValue as { [key: string]: SettingsValue };
  }

  const stringValue = String(rawValue);
  if (stringValue === "" && !field.secret) {
    return null;
  }

  return stringValue;
}

export function buildSdkSettingsPayload(
  schema: SettingsSchema,
  values: SettingsFormValues,
  dirty: SettingsDirtyState,
): SdkSettingsPayload {
  const payload: SdkSettingsPayload = {};

  for (const field of getSchemaFields(schema)) {
    if (dirty[field.key]) {
      payload[field.key] = coerceFieldValue(field, values[field.key]);
    }
  }

  return payload;
}

function isFieldVisibleInView(
  field: SettingsFieldSchema,
  view: SettingsView,
): boolean {
  return VIEW_PROMINENCES[view].has(field.prominence);
}

/** Return sections with fields filtered for the current view tier.
 *  Specially-rendered fields are excluded from the generic list. */
export function getVisibleSettingsSections(
  schema: SettingsSchema,
  values: SettingsFormValues,
  view: SettingsView,
  excludeKeys: Set<string> = SPECIALLY_RENDERED_KEYS,
): SettingsSectionSchema[] {
  return schema.sections
    .map((section) => ({
      ...section,
      fields: section.fields.filter(
        (field) =>
          !excludeKeys.has(field.key) &&
          isFieldVisibleInView(field, view) &&
          isSettingsFieldVisible(field, values),
      ),
    }))
    .filter((section) => section.fields.length > 0);
}

/** Whether the schema has any fields visible in the "advanced" tier. */
export function hasAdvancedSettings(schema: SettingsSchema | null): boolean {
  if (!schema) return false;
  return getSchemaFields(schema).some((f) => f.prominence === "major");
}

/** Whether the schema has any "minor" prominence fields. */
export function hasMinorSettings(schema: SettingsSchema | null): boolean {
  if (!schema) return false;
  return getSchemaFields(schema).some((f) => f.prominence === "minor");
}
