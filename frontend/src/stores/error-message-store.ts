import { create } from "zustand";

interface ErrorMessageState {
  errorMessage: string | null;
  isPersistent: boolean;
}

interface ErrorMessageActions {
  setErrorMessage: (message: string, persistent?: boolean) => void;
  removeErrorMessage: (force?: boolean) => void;
}

type ErrorMessageStore = ErrorMessageState & ErrorMessageActions;

const initialState: ErrorMessageState = {
  errorMessage: null,
  isPersistent: false,
};

export const useErrorMessageStore = create<ErrorMessageStore>((set, get) => ({
  ...initialState,

  setErrorMessage: (message: string, persistent: boolean = false) =>
    set(() => ({
      errorMessage: message,
      isPersistent: persistent,
    })),

  removeErrorMessage: (force: boolean = false) => {
    const { isPersistent } = get();
    if (isPersistent && !force) {
      return;
    }
    set(() => ({
      errorMessage: null,
      isPersistent: false,
    }));
  },
}));
