import { Outlet } from "react-router";

export default function OnboardingLayout() {
  return (
    <div
      data-testid="onboarding-layout"
      className="min-h-screen bg-[#0D0F11] flex flex-col items-center justify-center"
    >
      <Outlet />
    </div>
  );
}
