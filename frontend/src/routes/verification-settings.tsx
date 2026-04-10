import { SdkSectionPage } from "#/components/features/settings/sdk-settings/sdk-section-page";
import { createPermissionGuard } from "#/utils/org/permission-guard";

function VerificationSettingsScreen() {
  return (
    <SdkSectionPage
      sectionKeys={["verification"]}
      testId="verification-settings-screen"
    />
  );
}

export const clientLoader = createPermissionGuard("view_llm_settings");

export default VerificationSettingsScreen;
