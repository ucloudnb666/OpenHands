import { create } from "zustand";
import { devtools } from "zustand/middleware";

const SESSION_STORAGE_KEY = "selectedOrgId";

interface SelectedOrganizationState {
  organizationId: string | null;
}

interface SelectedOrganizationActions {
  setOrganizationId: (orgId: string | null) => void;
}

type SelectedOrganizationStore = SelectedOrganizationState &
  SelectedOrganizationActions;

const initialState: SelectedOrganizationState = {
  organizationId: sessionStorage.getItem(SESSION_STORAGE_KEY),
};

export const useSelectedOrganizationStore = create<SelectedOrganizationStore>()(
  devtools(
    (set) => ({
      ...initialState,
      setOrganizationId: (organizationId) => {
        if (organizationId) {
          sessionStorage.setItem(SESSION_STORAGE_KEY, organizationId);
        } else {
          sessionStorage.removeItem(SESSION_STORAGE_KEY);
        }
        set({ organizationId });
      },
    }),
    { name: "SelectedOrganizationStore" },
  ),
);

export const getSelectedOrganizationIdFromStore = (): string | null =>
  useSelectedOrganizationStore.getState().organizationId;
