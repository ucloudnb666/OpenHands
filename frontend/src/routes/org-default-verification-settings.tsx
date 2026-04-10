import { SdkSectionPage } from "#/components/features/settings/sdk-settings/sdk-section-page";
import { OrgDefaultsBanner } from "#/components/features/settings/org-defaults-banner";
import { createPermissionGuard } from "#/utils/org/permission-guard";

const renderOrgDefaultsBanner = () => <OrgDefaultsBanner />;

function OrgDefaultVerificationSettingsScreen() {
  return (
    <SdkSectionPage
      scope="org"
      sectionKeys={["verification"]}
      header={renderOrgDefaultsBanner}
      testId="org-default-verification-settings-screen"
    />
  );
}

export const clientLoader = createPermissionGuard(
  "edit_llm_settings",
  "/settings/verification",
);

export default OrgDefaultVerificationSettingsScreen;
