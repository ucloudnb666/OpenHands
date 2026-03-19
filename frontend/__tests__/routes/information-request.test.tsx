import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router";
import InformationRequest from "#/routes/information-request";

// Mock useNavigate
const mockNavigate = vi.fn();
vi.mock("react-router", async () => {
  const actual = await vi.importActual("react-router");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// Mock useTracking to avoid QueryClient dependency
vi.mock("#/hooks/use-tracking", () => ({
  useTracking: () => ({
    trackEnterpriseLeadFormSubmitted: vi.fn(),
  }),
}));

describe("InformationRequest", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderWithRouter = () => {
    return render(
      <MemoryRouter>
        <InformationRequest />
      </MemoryRouter>,
    );
  };

  it("should render the page", () => {
    renderWithRouter();

    expect(screen.getByTestId("information-request-page")).toBeInTheDocument();
  });

  it("should render the logo", () => {
    renderWithRouter();

    const page = screen.getByTestId("information-request-page");
    const logo = page.querySelector("svg");
    expect(logo).toBeInTheDocument();
  });

  it("should render the page title", () => {
    renderWithRouter();

    expect(screen.getByText("ENTERPRISE$GET_OPENHANDS_TITLE")).toBeInTheDocument();
  });

  it("should render the page subtitle", () => {
    renderWithRouter();

    expect(screen.getByText("ENTERPRISE$GET_OPENHANDS_SUBTITLE")).toBeInTheDocument();
  });

  it("should render SaaS card", () => {
    renderWithRouter();

    expect(screen.getByText("ENTERPRISE$SAAS_TITLE")).toBeInTheDocument();
    expect(screen.getByText("ENTERPRISE$SAAS_DESCRIPTION")).toBeInTheDocument();
  });

  it("should render Self-hosted card", () => {
    renderWithRouter();

    expect(screen.getByText("ENTERPRISE$SELF_HOSTED_TITLE")).toBeInTheDocument();
    expect(screen.getByText("ENTERPRISE$SELF_HOSTED_CARD_DESCRIPTION")).toBeInTheDocument();
  });

  it("should render SaaS features", () => {
    renderWithRouter();

    expect(screen.getByText("ENTERPRISE$SAAS_FEATURE_NO_INFRASTRUCTURE")).toBeInTheDocument();
    expect(screen.getByText("ENTERPRISE$SAAS_FEATURE_SSO")).toBeInTheDocument();
    expect(screen.getByText("ENTERPRISE$SAAS_FEATURE_ACCESS_ANYWHERE")).toBeInTheDocument();
    expect(screen.getByText("ENTERPRISE$SAAS_FEATURE_AUTO_UPDATES")).toBeInTheDocument();
  });

  it("should render Self-hosted features", () => {
    renderWithRouter();

    expect(screen.getByText("ENTERPRISE$SELF_HOSTED_FEATURE_ON_PREMISES")).toBeInTheDocument();
    expect(screen.getByText("ENTERPRISE$SELF_HOSTED_FEATURE_DATA_CONTROL")).toBeInTheDocument();
    expect(screen.getByText("ENTERPRISE$SELF_HOSTED_FEATURE_COMPLIANCE")).toBeInTheDocument();
    expect(screen.getByText("ENTERPRISE$SELF_HOSTED_FEATURE_SUPPORT")).toBeInTheDocument();
  });

  it("should render two Learn More buttons", () => {
    renderWithRouter();

    const learnMoreButtons = screen.getAllByText("ENTERPRISE$LEARN_MORE");
    expect(learnMoreButtons).toHaveLength(2);
  });

  it("should render back button", () => {
    renderWithRouter();

    expect(screen.getByText("COMMON$BACK")).toBeInTheDocument();
  });

  it("should navigate to /login when back button is clicked", async () => {
    const user = userEvent.setup();
    renderWithRouter();

    const backButton = screen.getByText("COMMON$BACK");
    await user.click(backButton);

    expect(mockNavigate).toHaveBeenCalledWith("/login");
  });

  it("should show SaaS form when SaaS Learn More is clicked", async () => {
    const user = userEvent.setup();
    renderWithRouter();

    // Click the first Learn More button (SaaS)
    const learnMoreButtons = screen.getAllByText("ENTERPRISE$LEARN_MORE");
    await user.click(learnMoreButtons[0]);

    // Form should now be visible
    expect(screen.getByTestId("information-request-form")).toBeInTheDocument();
    expect(screen.getByText("ENTERPRISE$FORM_SAAS_TITLE")).toBeInTheDocument();
  });

  it("should show Self-hosted form when Self-hosted Learn More is clicked", async () => {
    const user = userEvent.setup();
    renderWithRouter();

    // Click the second Learn More button (Self-hosted)
    const learnMoreButtons = screen.getAllByText("ENTERPRISE$LEARN_MORE");
    await user.click(learnMoreButtons[1]);

    // Form should now be visible
    expect(screen.getByTestId("information-request-form")).toBeInTheDocument();
    expect(screen.getByText("ENTERPRISE$FORM_SELF_HOSTED_TITLE")).toBeInTheDocument();
  });

  it("should return to card selection when form back button is clicked", async () => {
    const user = userEvent.setup();
    renderWithRouter();

    // Click Learn More to show form
    const learnMoreButtons = screen.getAllByText("ENTERPRISE$LEARN_MORE");
    await user.click(learnMoreButtons[0]);

    // Click back button in form
    const backButton = screen.getByRole("button", { name: "COMMON$BACK" });
    await user.click(backButton);

    // Should be back to card selection view
    expect(screen.queryByTestId("information-request-form")).not.toBeInTheDocument();
    expect(screen.getByText("ENTERPRISE$GET_OPENHANDS_TITLE")).toBeInTheDocument();
  });

  it("should have accessible Learn More buttons with aria-label", () => {
    renderWithRouter();

    const saasButton = screen.getByRole("button", {
      name: "ENTERPRISE$LEARN_MORE ENTERPRISE$SAAS_TITLE",
    });
    const selfHostedButton = screen.getByRole("button", {
      name: "ENTERPRISE$LEARN_MORE ENTERPRISE$SELF_HOSTED_TITLE",
    });

    expect(saasButton).toBeInTheDocument();
    expect(selfHostedButton).toBeInTheDocument();
  });
});
