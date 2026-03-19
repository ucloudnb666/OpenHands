import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { I18nKey } from "#/i18n/declaration";
import { Card } from "#/ui/card";
import { Text } from "#/ui/typography";
import { BrandButton } from "#/components/features/settings/brand-button";
import {
  InformationRequestForm,
  RequestType,
} from "#/components/features/onboarding/information-request-form";
import OpenHandsLogoWhite from "#/assets/branding/openhands-logo-white.svg?react";
import CloudIcon from "#/icons/cloud.svg?react";
import StackedIcon from "#/icons/stacked.svg?react";

interface FeatureListProps {
  features: string[];
}

function FeatureList({ features }: FeatureListProps) {
  return (
    <ul className="flex flex-col gap-2">
      {features.map((feature, index) => (
        <li key={`feature-${index}`} className="flex items-center gap-2">
          <span className="text-[#8C8C8C]">•</span>
          <Text className="text-[#8C8C8C]">{feature}</Text>
        </li>
      ))}
    </ul>
  );
}

interface EnterpriseCardProps {
  icon: React.ReactNode;
  title: string;
  description: string;
  features: string[];
  onLearnMore: () => void;
  learnMoreLabel: string;
}

function EnterpriseCard({
  icon,
  title,
  description,
  features,
  onLearnMore,
  learnMoreLabel,
}: EnterpriseCardProps) {
  return (
    <Card theme="dark" hover="elevated" className="flex-1 flex-col p-6 gap-4">
      <div className="w-10 h-10">{icon}</div>
      <h3 className="text-lg font-semibold text-white">{title}</h3>
      <Text className="text-[#8C8C8C]">{description}</Text>
      <FeatureList features={features} />
      <button
        type="button"
        onClick={onLearnMore}
        className="mt-2 w-fit px-6 py-2.5 text-sm rounded-sm bg-[#050505] text-white border border-[#242424] hover:bg-white hover:text-black transition-colors"
      >
        {learnMoreLabel}
      </button>
    </Card>
  );
}

export default function InformationRequest() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [selectedRequestType, setSelectedRequestType] =
    useState<RequestType | null>(null);

  const handleBack = () => {
    navigate("/login");
  };

  const handleLearnMore = (type: RequestType) => {
    setSelectedRequestType(type);
  };

  const handleFormBack = () => {
    setSelectedRequestType(null);
  };

  const saasFeatures = [
    t(I18nKey.ENTERPRISE$SAAS_FEATURE_NO_INFRASTRUCTURE),
    t(I18nKey.ENTERPRISE$SAAS_FEATURE_SSO),
    t(I18nKey.ENTERPRISE$SAAS_FEATURE_ACCESS_ANYWHERE),
    t(I18nKey.ENTERPRISE$SAAS_FEATURE_AUTO_UPDATES),
  ];

  const selfHostedFeatures = [
    t(I18nKey.ENTERPRISE$SELF_HOSTED_FEATURE_ON_PREMISES),
    t(I18nKey.ENTERPRISE$SELF_HOSTED_FEATURE_DATA_CONTROL),
    t(I18nKey.ENTERPRISE$SELF_HOSTED_FEATURE_COMPLIANCE),
    t(I18nKey.ENTERPRISE$SELF_HOSTED_FEATURE_SUPPORT),
  ];

  // Show form if a request type is selected
  if (selectedRequestType) {
    return (
      <div
        data-testid="information-request-page"
        className="w-full max-w-4xl flex flex-col items-center gap-8 p-6"
      >
        <InformationRequestForm
          requestType={selectedRequestType}
          onBack={handleFormBack}
        />
      </div>
    );
  }

  return (
    <div
      data-testid="information-request-page"
      className="w-full max-w-4xl flex flex-col items-center gap-8 p-6"
    >
      {/* Logo */}
      <OpenHandsLogoWhite width={55} height={55} />

      {/* Header */}
      <div className="text-center flex flex-col gap-3">
        <h1 className="text-2xl font-bold text-white">
          {t(I18nKey.ENTERPRISE$GET_OPENHANDS_TITLE)}
        </h1>
        <Text className="text-[#8C8C8C] max-w-lg">
          {t(I18nKey.ENTERPRISE$GET_OPENHANDS_SUBTITLE)}
        </Text>
      </div>

      {/* Cards */}
      <div className="w-full flex flex-col md:flex-row gap-4">
        <EnterpriseCard
          icon={<CloudIcon className="w-10 h-10" />}
          title={t(I18nKey.ENTERPRISE$SAAS_TITLE)}
          description={t(I18nKey.ENTERPRISE$SAAS_DESCRIPTION)}
          features={saasFeatures}
          onLearnMore={() => handleLearnMore("saas")}
          learnMoreLabel={t(I18nKey.ENTERPRISE$LEARN_MORE)}
        />
        <EnterpriseCard
          icon={<StackedIcon className="w-10 h-10" />}
          title={t(I18nKey.ENTERPRISE$SELF_HOSTED_TITLE)}
          description={t(I18nKey.ENTERPRISE$SELF_HOSTED_DESCRIPTION)}
          features={selfHostedFeatures}
          onLearnMore={() => handleLearnMore("self-hosted")}
          learnMoreLabel={t(I18nKey.ENTERPRISE$LEARN_MORE)}
        />
      </div>

      {/* Back Button */}
      <BrandButton
        type="button"
        variant="secondary"
        onClick={handleBack}
        className="px-6 py-2.5 bg-[#050505] text-white border border-[#242424] hover:bg-white hover:text-black"
      >
        {t(I18nKey.COMMON$BACK)}
      </BrandButton>
    </div>
  );
}
