import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { I18nKey } from "#/i18n/declaration";
import { useTracking } from "#/hooks/use-tracking";
import { Card } from "#/ui/card";
import { Text } from "#/ui/typography";
import { FormInput } from "./form-input";
import OpenHandsLogoWhite from "#/assets/branding/openhands-logo-white.svg?react";
import CloudIcon from "#/icons/cloud-minimal.svg?react";
import StackedIcon from "#/icons/stacked.svg?react";

export type RequestType = "saas" | "self-hosted";

interface InformationRequestFormProps {
  requestType: RequestType;
  onBack: () => void;
}

export function InformationRequestForm({
  requestType,
  onBack,
}: InformationRequestFormProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { trackEnterpriseLeadFormSubmitted } = useTracking();
  const [formData, setFormData] = useState({
    name: "",
    company: "",
    email: "",
    message: "",
  });
  const [hasAttemptedSubmit, setHasAttemptedSubmit] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setHasAttemptedSubmit(true);

    // Check if all required fields are filled
    const isValid =
      formData.name.trim() &&
      formData.company.trim() &&
      formData.email.trim() &&
      formData.message.trim();

    if (!isValid) {
      return;
    }

    // TODO: Implement actual form submission API call
    // Track form submission in PostHog
    trackEnterpriseLeadFormSubmitted({
      requestType,
      name: formData.name.trim(),
      company: formData.company.trim(),
      email: formData.email.trim(),
      message: formData.message.trim(),
    });

    // Navigate to homepage with state to show confirmation modal
    navigate("/", { state: { showRequestSubmittedModal: true } });
  };

  const isSaas = requestType === "saas";

  const title = isSaas
    ? t(I18nKey.ENTERPRISE$FORM_SAAS_TITLE)
    : t(I18nKey.ENTERPRISE$FORM_SELF_HOSTED_TITLE);

  const subtitle = isSaas
    ? t(I18nKey.ENTERPRISE$FORM_SAAS_SUBTITLE)
    : t(I18nKey.ENTERPRISE$FORM_SELF_HOSTED_SUBTITLE);

  const cardTitle = isSaas
    ? t(I18nKey.ENTERPRISE$SAAS_TITLE)
    : t(I18nKey.ENTERPRISE$SELF_HOSTED_TITLE);

  const cardDescription = isSaas
    ? t(I18nKey.ENTERPRISE$SAAS_DESCRIPTION)
    : t(I18nKey.ENTERPRISE$SELF_HOSTED_DESCRIPTION);

  const messagePlaceholder = isSaas
    ? t(I18nKey.ENTERPRISE$FORM_MESSAGE_SAAS_PLACEHOLDER)
    : t(I18nKey.ENTERPRISE$FORM_MESSAGE_SELF_HOSTED_PLACEHOLDER);

  return (
    <div
      data-testid="information-request-form"
      className="w-full max-w-[896px] flex flex-col items-center gap-8"
    >
      {/* Header */}
      <div className="w-full flex flex-col items-center gap-4">
        <OpenHandsLogoWhite width={56} height={56} />
        <div className="text-center flex flex-col gap-2">
          <h1 className="text-2xl font-semibold text-white">{title}</h1>
          <Text className="text-[#8C8C8C] leading-5">{subtitle}</Text>
        </div>
      </div>

      {/* Content: Form + Card */}
      <div className="w-full flex flex-col md:flex-row gap-8">
        {/* Form */}
        <form
          onSubmit={handleSubmit}
          className="flex-1 flex flex-col gap-4 w-full md:max-w-[544px]"
        >
          <FormInput
            id="name"
            label={t(I18nKey.ENTERPRISE$FORM_NAME_LABEL)}
            value={formData.name}
            placeholder={t(I18nKey.ENTERPRISE$FORM_NAME_PLACEHOLDER)}
            required
            showError={hasAttemptedSubmit}
            onChange={(value) =>
              setFormData((prev) => ({ ...prev, name: value }))
            }
          />

          <FormInput
            id="company"
            label={t(I18nKey.ENTERPRISE$FORM_COMPANY_LABEL)}
            value={formData.company}
            placeholder={t(I18nKey.ENTERPRISE$FORM_COMPANY_PLACEHOLDER)}
            required
            showError={hasAttemptedSubmit}
            onChange={(value) =>
              setFormData((prev) => ({ ...prev, company: value }))
            }
          />

          <FormInput
            id="email"
            label={t(I18nKey.ENTERPRISE$FORM_EMAIL_LABEL)}
            type="email"
            value={formData.email}
            placeholder={t(I18nKey.ENTERPRISE$FORM_EMAIL_PLACEHOLDER)}
            required
            showError={hasAttemptedSubmit}
            onChange={(value) =>
              setFormData((prev) => ({ ...prev, email: value }))
            }
          />

          <FormInput
            id="message"
            label={t(I18nKey.ENTERPRISE$FORM_MESSAGE_LABEL)}
            value={formData.message}
            placeholder={messagePlaceholder}
            rows={4}
            required
            showError={hasAttemptedSubmit}
            onChange={(value) =>
              setFormData((prev) => ({ ...prev, message: value }))
            }
          />

          {/* Buttons */}
          <div
            className="flex gap-4 mt-4"
            role="group"
            aria-label="Form actions"
          >
            <button
              type="button"
              onClick={onBack}
              aria-label={t(I18nKey.COMMON$BACK)}
              className="flex-1 px-6 py-2.5 text-sm rounded bg-transparent text-white border border-[#242424] hover:bg-[#1a1a1a] transition-colors"
            >
              {t(I18nKey.COMMON$BACK)}
            </button>
            <button
              type="submit"
              aria-label={t(I18nKey.ENTERPRISE$FORM_SUBMIT)}
              className="flex-1 px-6 py-2.5 text-sm rounded bg-white text-black border border-white hover:bg-gray-100 transition-colors"
            >
              {t(I18nKey.ENTERPRISE$FORM_SUBMIT)}
            </button>
          </div>
        </form>

        {/* CTA Card */}
        <Card
          theme="dark"
          gradient="standard"
          className="w-full md:w-80 flex-col p-6 gap-4"
        >
          <div className="w-10 h-10">
            {isSaas ? (
              <CloudIcon className="w-10 h-10" />
            ) : (
              <StackedIcon className="w-10 h-10" />
            )}
          </div>
          <h3 className="text-xl font-semibold leading-7 text-[#FAFAFA]">
            {cardTitle}
          </h3>
          <Text className="text-[#8C8C8C]">{cardDescription}</Text>
        </Card>
      </div>
    </div>
  );
}
