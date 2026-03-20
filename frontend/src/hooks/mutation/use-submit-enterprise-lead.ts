import { useMutation } from "@tanstack/react-query";
import { openHands } from "#/api/open-hands-axios";

export interface EnterpriseLeadFormData {
  requestType: "saas" | "self-hosted";
  name: string;
  company: string;
  email: string;
  message: string;
}

/**
 * Hook for submitting enterprise lead capture forms.
 * Handles the API call and provides loading/error states.
 */
export const useSubmitEnterpriseLead = () =>
  useMutation({
    mutationFn: async (formData: EnterpriseLeadFormData) => {
      const { data } = await openHands.post<{
        id: string;
        status: string;
        created_at: string;
      }>(
        "/api/forms/submit",
        {
          form_type: "enterprise_lead",
          answers: {
            request_type: formData.requestType,
            name: formData.name,
            company: formData.company,
            email: formData.email,
            message: formData.message,
          },
        },
        { withCredentials: true },
      );
      return data;
    },
  });
