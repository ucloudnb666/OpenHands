import { Page, Locator, expect } from "@playwright/test";
import { BasePage } from "./BasePage";

/**
 * Page object for the Home screen where users start new conversations
 * and view recent conversations.
 */
export class HomePage extends BasePage {
  // Main containers
  readonly homeScreen: Locator;
  readonly newConversationSection: Locator;
  readonly recentConversationsSection: Locator;

  // User avatar and menu
  readonly userAvatar: Locator;
  readonly accountSettingsMenu: Locator;

  // Repository selection
  readonly repoSelector: Locator;
  readonly repoSearchInput: Locator;

  constructor(page: Page) {
    super(page);

    this.homeScreen = page.getByTestId("home-screen");
    this.newConversationSection = page.getByTestId("home-screen-new-conversation-section");
    this.recentConversationsSection = page.getByTestId("home-screen-recent-conversations-section");
    this.userAvatar = page.getByTestId("user-avatar");
    this.accountSettingsMenu = page.getByTestId("account-settings-context-menu");
    this.repoSelector = page.locator('[data-testid*="repo"]').first();
    this.repoSearchInput = page.locator('input[placeholder*="repository"], input[placeholder*="repo"]').first();
  }

  /**
   * Navigate to the home page
   */
  async goto(): Promise<void> {
    await super.goto("/");
    await this.waitForHomeScreen();
  }

  /**
   * Wait for the home screen to be fully loaded
   */
  async waitForHomeScreen(): Promise<void> {
    await expect(this.homeScreen).toBeVisible({ timeout: 30_000 });
    await this.waitForNetworkIdle();
  }

  /**
   * Check if user is logged in by verifying home screen is visible
   */
  async isLoggedIn(): Promise<boolean> {
    try {
      await expect(this.homeScreen).toBeVisible({ timeout: 10_000 });
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Select a repository by searching for it
   * @param repoUrl - Full repository URL (e.g., https://github.com/OpenHands/deploy)
   */
  async selectRepository(repoUrl: string): Promise<void> {
    // Extract repo name from URL
    const repoName = repoUrl.split("/").slice(-2).join("/");

    // Look for repository selector/input
    const repoInput = this.page.locator('input[placeholder*="repository"], input[placeholder*="search"]').first();
    const repoSelector = this.page.locator('[class*="repo"], [data-testid*="repo"]').first();

    // Try to find and interact with repo selection
    if (await repoInput.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await repoInput.fill(repoName);
      await this.page.waitForTimeout(1000); // Wait for search results
    } else if (await repoSelector.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await repoSelector.click();
      await this.page.waitForTimeout(500);
    }

    // Click on the repository in the dropdown/list
    const repoOption = this.page.locator(`text=${repoName}`).first();
    if (await repoOption.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await repoOption.click();
    }
  }

  /**
   * Start a new conversation
   * @param buttonId - Optional test ID of the button to click (default: 'launch-new-conversation-button')
   */
  async startNewConversation(buttonId: string = 'launch-new-conversation-button'): Promise<void> {
    const startButton = this.page.getByTestId(buttonId)
    if (await startButton.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await startButton.click();
    }

    // Wait for conversation/chat interface to load
    await this.page.waitForURL(/conversation|chat|app/, { timeout: 30_000 }).catch(() => {});
  }

  /**
   * Open user settings menu
   * Note: The menu appears on hover in non-mobile mode, not on click
   */
  async openUserMenu(): Promise<void> {
    // The user menu is triggered by hover, not click, in non-mobile mode
    await this.userAvatar.hover();
    await expect(this.accountSettingsMenu).toBeVisible({ timeout: 5_000 });
  }

  /**
   * Get list of recent conversations
   */
  async getRecentConversations(): Promise<string[]> {
    await this.waitForElement(this.recentConversationsSection);
    const conversations = await this.recentConversationsSection.locator("a, button, [role='button']").allTextContents();
    return conversations.filter((text) => text.trim().length > 0);
  }
}
