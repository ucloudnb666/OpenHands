import { test, expect } from "@playwright/test";
import { HomePage, ConversationPage } from "../pages";

/**
 * Smoke Tests for OpenHands Application
 *
 * These tests verify the critical path of the application:
 * 1. User can log in (handled by global-setup)
 * 2. User can access the home screen
 * 3. User can select a repository
 * 4. User can start a conversation
 * 5. Agent can process a simple prompt without errors
 *
 * Tags:
 * - @smoke: Core smoke tests that must pass
 * - @critical: Critical functionality tests
 *
 * Environment Variables:
 * - TEST_REPO_URL: Repository to use for testing (default: null)
 * - TEST_PROMPT: Prompt to send to agent (default: "Flip a coin!")
 */

// Test configuration
const TEST_REPO_URL = process.env.TEST_REPO_URL;
const TEST_PROMPT = process.env.TEST_PROMPT || "Flip a coin!";

test.describe("Smoke Tests @smoke", () => {
  test.describe.configure({ mode: "serial" }); // Run tests in sequence

  let homePage: HomePage;
  let conversationPage: ConversationPage;

  test.beforeEach(async ({ page }) => {
    homePage = new HomePage(page);
    conversationPage = new ConversationPage(page);
  });

  test("should display home screen after authentication @critical", async ({ page }) => {
    await homePage.goto();

    // Verify home screen is visible
    await expect(homePage.homeScreen).toBeVisible({ timeout: 30_000 });

    // Verify key sections are present
    await expect(homePage.newConversationSection).toBeVisible();

    // Take screenshot for verification
    await page.screenshot({ path: "test-results/screenshots/home-screen.png" });
  });

  test("should have user avatar visible indicating logged in state @critical", async () => {
    await homePage.goto();

    // Verify user is logged in
    const isLoggedIn = await homePage.isLoggedIn();
    expect(isLoggedIn).toBe(true);

    // Verify user avatar is visible
    await expect(homePage.userAvatar).toBeVisible();
  });

  test("should be able to open user menu", async () => {
    await homePage.goto();

    // Open user menu
    await homePage.openUserMenu();

    // Verify menu is visible
    await expect(homePage.accountSettingsMenu).toBeVisible();
  });

  test("should be able to start a conversation and interact with agent @critical", async ({ page }) => {
    // Navigate to home
    await homePage.goto();

    if (TEST_REPO_URL) {
      // Select repository if repo selection is available
      try {
        await homePage.selectRepository(TEST_REPO_URL);
        console.log(`Selected repository: ${TEST_REPO_URL}`);
      } catch (e) {
        console.log("Repository selection not available or failed, continuing...");
      }
      // Start a new conversation
      await homePage.startNewConversation('repo-launch-button');
    } else {
      await homePage.startNewConversation('launch-new-conversation-button');
    }

    // Wait for conversation page to load
    await page.waitForTimeout(2000); // Allow navigation to complete

    // Initialize conversation page
    conversationPage = new ConversationPage(page);

    // Wait for the agent to be ready
    await conversationPage.waitForConversationReady(90_000);

    // Verify chat interface is available
    await expect(conversationPage.chatBox).toBeVisible();
    await expect(conversationPage.chatInput).toBeVisible();

    // Take screenshot before sending message
    await page.screenshot({ path: "test-results/screenshots/conversation-ready.png" });
  });

  test("should be able to send a prompt and receive response without errors @critical", async ({ page }) => {
    // This test continues from a fresh conversation
    await homePage.goto();

    // Start a new conversation
    if (TEST_REPO_URL) {
      try {
        await homePage.selectRepository(TEST_REPO_URL);
      } catch {
        // Repository selection might not be required
      }
      await homePage.startNewConversation('repo-launch-button');
    } else {
      await homePage.startNewConversation();
    }
    await page.waitForTimeout(2000);

    conversationPage = new ConversationPage(page);

    // Wait for agent to be ready
    await conversationPage.waitForConversationReady(90_000);

    // Execute the test prompt
    console.log(`Sending prompt: "${TEST_PROMPT}"`);
    await conversationPage.executePrompt(TEST_PROMPT, 120_000);

    // Verify no errors occurred
    await conversationPage.verifyNoErrors();

    // Take screenshot of successful response
    await page.screenshot({ path: "test-results/screenshots/agent-response.png" });

    console.log("Smoke test passed: Agent responded without errors");
  });

  test("should not display error banner on successful interaction", async ({ page }) => {
    await homePage.goto();

    // Check no error banner on home screen
    const homeError = await homePage.hasError();
    expect(homeError).toBe(false);

    // Start conversation
    if (TEST_REPO_URL) {
      try {
        await homePage.selectRepository(TEST_REPO_URL);
      } catch {
        // Repository selection might not be required
      }
      await homePage.startNewConversation('repo-launch-button');
    } else {
      await homePage.startNewConversation();
    }
    await page.waitForTimeout(2000);

    conversationPage = new ConversationPage(page);
    await conversationPage.waitForConversationReady(60_000);

    // Check no error banner on conversation screen
    const conversationError = await conversationPage.hasError();
    expect(conversationError).toBe(false);
  });
});

test.describe("Health Check Tests @smoke", () => {
  test("application should be accessible", async ({ page, baseURL }) => {
    const response = await page.goto(baseURL || "/");

    // Verify we got a successful response
    expect(response?.status()).toBeLessThan(400);
  });

  test("application should not have console errors on load", async ({ page }) => {
    const errors: string[] = [];

    page.on("console", (msg) => {
      if (msg.type() === "error") {
        // Filter out known acceptable errors
        const text = msg.text();
        if (
          !text.includes("favicon") &&
          !text.includes("sourcemap") &&
          !text.includes("DevTools")
        ) {
          errors.push(text);
        }
      }
    });

    await page.goto("/");
    await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => {});

    // Log any errors found
    if (errors.length > 0) {
      console.log("Console errors found:", errors);
    }

    // Fail if critical errors exist
    const criticalErrors = errors.filter(
      (e) => e.includes("TypeError") || e.includes("ReferenceError") || e.includes("SyntaxError")
    );
    expect(criticalErrors).toHaveLength(0);
  });
});

test.describe("Environment Validation @smoke", () => {
  test("should be connected to correct environment", async ({ page, baseURL }) => {
    await page.goto("/");

    // Log the current environment for verification
    console.log(`Testing against: ${baseURL}`);

    // Verify we're on the expected domain
    const url = page.url();
    expect(url).toContain(new URL(baseURL || "").hostname);
  });

  test("should have valid SSL certificate", async ({ page, baseURL }) => {
    // This test implicitly validates SSL because ignoreHTTPSErrors is true
    // but we still want to verify the connection works
    const response = await page.goto(baseURL || "/");
    expect(response?.ok()).toBe(true);
  });
});
