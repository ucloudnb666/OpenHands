import { useTranslation } from "react-i18next";
import { I18nKey } from "#/i18n/declaration";
import { ModalBackdrop } from "#/components/shared/modals/modal-backdrop";

interface RequestSubmittedModalProps {
  onClose: () => void;
}

export function RequestSubmittedModal({ onClose }: RequestSubmittedModalProps) {
  const { t } = useTranslation();

  return (
    <ModalBackdrop
      onClose={onClose}
      aria-label={t(I18nKey.ENTERPRISE$REQUEST_SUBMITTED_TITLE)}
    >
      <div
        data-testid="request-submitted-modal"
        className="w-[448px] bg-black rounded-md border border-[#242424] border-t-[#242424]"
        style={{
          boxShadow:
            "0px 4px 6px -4px rgba(0, 0, 0, 0.1), 0px 10px 15px -3px rgba(0, 0, 0, 0.1)",
        }}
      >
        {/* Header with close button */}
        <div className="relative p-6 pb-0">
          <button
            type="button"
            onClick={onClose}
            aria-label={t(I18nKey.MODAL$CLOSE_BUTTON_LABEL)}
            className="absolute top-[17px] right-[17px] w-4 h-4 flex items-center justify-center opacity-70 hover:opacity-100 transition-opacity rounded-sm"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M12 4L4 12M4 4L12 12"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>

          {/* Title and description */}
          <div className="flex flex-col gap-1.5 pr-8">
            <h2 className="text-lg font-semibold text-white leading-[18px] tracking-[-0.45px]">
              {t(I18nKey.ENTERPRISE$REQUEST_SUBMITTED_TITLE)}
            </h2>
            <p className="text-sm text-[#8C8C8C] leading-5">
              {t(I18nKey.ENTERPRISE$REQUEST_SUBMITTED_DESCRIPTION)}
            </p>
          </div>
        </div>

        {/* Footer with Done button */}
        <div className="p-6 pt-4 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            aria-label={t(I18nKey.ENTERPRISE$DONE_BUTTON)}
            className="px-4 py-2 text-sm font-medium bg-white text-black rounded hover:bg-gray-100 transition-colors"
          >
            {t(I18nKey.ENTERPRISE$DONE_BUTTON)}
          </button>
        </div>
      </div>
    </ModalBackdrop>
  );
}
