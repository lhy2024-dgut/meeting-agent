import { APIRequestContext, expect, Locator, Page, test } from "@playwright/test";

import { waitForApiJson, waitForAppReady } from "./helpers";

type MeetingListResponse = {
  items: Array<{ id: number }>;
};

type TranscriptResponse = {
  segments: Array<{ text: string }>;
};

function compactText(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

async function switchToCrossMeetingMode(page: Page) {
  const modeButtons = page.locator(".segmented-toggle button");
  await expect(modeButtons).toHaveCount(2);
  await modeButtons.nth(1).click();
}

async function submitCrossMeetingQuery(page: Page, query: string): Promise<Locator> {
  const input = page.locator("textarea.input-shell").first();
  const sendButton = page.locator("button.primary-button").first();
  const assistantBubbles = page.locator(".chat-bubble-assistant");
  const assistantCountBefore = await assistantBubbles.count();

  await expect(input).toBeVisible();
  await expect(input).toBeEnabled({ timeout: 30_000 });
  await expect(sendButton).toBeEnabled({ timeout: 30_000 });

  await input.fill(query);
  await sendButton.click();

  await expect(assistantBubbles).toHaveCount(assistantCountBefore + 1, {
    timeout: 120_000,
  });

  const ragPanel = page.locator("details.rag-panel").last();
  await expect(ragPanel).toBeVisible({ timeout: 60_000 });
  await ragPanel.locator("summary").click();
  return ragPanel;
}

async function collectTranscriptQueries(request: APIRequestContext): Promise<string[]> {
  const meetings = await waitForApiJson<MeetingListResponse>(
    request,
    "/api/meetings?page=0&page_size=5",
  );
  const queries: string[] = [];

  for (const meeting of meetings.items) {
    const transcript = await waitForApiJson<TranscriptResponse>(
      request,
      `/api/meetings/${meeting.id}/transcript`,
    );
    const segment = transcript.segments.find((item) => compactText(item.text).length >= 12);
    if (!segment) {
      continue;
    }

    queries.push(compactText(segment.text).slice(0, 24));
    if (queries.length >= 3) {
      break;
    }
  }

  expect(queries.length).toBeGreaterThan(0);
  return queries;
}

async function findSourceHref(
  ragPanel: Locator,
  predicate: (href: string) => boolean,
): Promise<string | null> {
  const sourceLinks = ragPanel.locator("a.rag-source-link");
  const linkCount = await sourceLinks.count();

  for (let index = 0; index < linkCount; index += 1) {
    const href = await sourceLinks.nth(index).getAttribute("href");
    if (href && predicate(href)) {
      return href;
    }
  }

  return null;
}

test("cross-meeting source links navigate to highlighted meeting content", async ({
  page,
  request,
}) => {
  const queries = await collectTranscriptQueries(request);

  await waitForAppReady(page, "/chat");
  await switchToCrossMeetingMode(page);

  const ragPanel = await submitCrossMeetingQuery(page, queries[0]);
  const firstSourceLink = ragPanel.locator("a.rag-source-link").first();
  await expect(firstSourceLink).toBeVisible({ timeout: 60_000 });

  const href = await firstSourceLink.getAttribute("href");
  expect(href).toBeTruthy();
  expect(href).toContain("/meetings/");
  expect(href).toContain("source=");
  expect(href).toContain("snippet=");

  const targetUrl = new URL(href ?? "", "http://127.0.0.1:3000");
  await page.goto(targetUrl.toString(), { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => undefined);

  await expect(page).toHaveURL(/\/meetings\/\d+\?source=.*snippet=.*/);
  await expect(page.locator(".source-focus-badge").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".source-highlight").first()).toBeVisible({ timeout: 30_000 });
});

test("cross-meeting transcript links resolve to transcript snippet highlights", async ({
  page,
  request,
}) => {
  const queries = await collectTranscriptQueries(request);

  await waitForAppReady(page, "/chat");
  await switchToCrossMeetingMode(page);

  let transcriptHref: string | null = null;

  for (const query of queries) {
    const ragPanel = await submitCrossMeetingQuery(page, query);
    transcriptHref = await findSourceHref(
      ragPanel,
      (href) => href.includes("/meetings/") && href.includes("source=transcript"),
    );
    if (transcriptHref) {
      break;
    }
  }

  expect(transcriptHref).toBeTruthy();
  expect(transcriptHref).toContain("source=transcript");

  const transcriptUrl = new URL(transcriptHref ?? "", "http://127.0.0.1:3000");
  const snippet = transcriptUrl.searchParams.get("snippet") ?? "";
  expect(snippet.length).toBeGreaterThanOrEqual(8);
  expect(snippet.length).toBeLessThanOrEqual(32);

  await page.goto(transcriptUrl.toString(), { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => undefined);

  await expect(page.locator(".source-focus-badge").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".source-fallback-badge")).toHaveCount(0);
  await expect(page.locator(".source-highlight").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".source-snippet-active").first()).toBeVisible({
    timeout: 30_000,
  });

  const activeText = (await page.locator(".source-snippet-active").first().textContent()) ?? "";
  expect(activeText.trim().length).toBeGreaterThan(0);
});
