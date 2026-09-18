// Headless verification for the application shell (A10).
// Needs a scratch stack with a FRESH database: reset, migrate, then run
// the backend on :8100 (VITE_API_PROXY) and `vite --port 5174`.
// Run: node verify.mjs [base]
// Journeys: empty home, seed, continue, wizard creation, stories catalog
// plus setup modal, library, settings, advance, player action submit,
// keyboard nav, theme, mobile, clean console.
import { chromium } from "playwright";

const base = process.argv[2] ?? "http://localhost:5174";
const apiBase = process.argv[3] ?? "http://localhost:8100";
const errors = [];

async function check(name, fn) {
  try {
    await fn();
    console.log(`ok: ${name}`);
  } catch (error) {
    errors.push(name);
    console.log(`FAIL: ${name}: ${String(error.message).split("\n")[0]}`);
  }
}
function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function api(path, options = {}) {
  const response = await fetch(`${apiBase}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`${path} -> ${response.status}: ${(await response.text()).slice(0, 160)}`);
  }
  return response.json();
}

const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const consoleErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));

  await check("home loads with empty state", async () => {
    await page.goto(base, { waitUntil: "networkidle" });
    await page.getByText("Begin your first tale").waitFor({ timeout: 15000 });
  });

  await check("seed shows a continue story", async () => {
    await api("/api/v1/world/seed", { method: "POST" });
    await page.reload({ waitUntil: "networkidle" });
    await page.getByRole("button", { name: /Continue Story/ }).waitFor({ timeout: 15000 });
    consoleErrors.length = 0;
  });

  await check("continue opens story adventure", async () => {
    await page.getByRole("button", { name: /Continue Story/ }).click({ timeout: 12000 });
    await page.waitForURL(/\/stories\/.*\/(adventure|world)/, { timeout: 15000 });
    await page.locator("header nav").first().waitFor({ timeout: 15000 });
  });

  await check("advance renders scenes and beats", async () => {
    await page.getByRole("link", { name: "adventure" }).click({ timeout: 12000 });
    await page.getByText("no scene selected").waitFor({ timeout: 15000 });
    await page.getByRole("button", { name: /advance to/ }).click({ timeout: 12000 });
    await page.locator(".strip button").first().waitFor({ timeout: 60000 });
    await page.locator(".strip button").last().click({ timeout: 12000 });
    await page.locator(".beat").first().waitFor({ timeout: 15000 });
    const beats = await page.locator(".beat").count();
    assert(beats > 0, "expected at least one beat");
  });

  await check("player action submit queues without doubles", async () => {
    const catalog = await api("/api/v1/stories?status=all");
    const worldId = catalog.items[0].world_id;
    const status = await api(`/api/v1/simulation/status?world_id=${worldId}`);
    assert(status.latest_run_id, "no completed run to read scenes from");
    const apiScenes = await api(
      `/api/v1/stage1/scenes?phase_run_id=${status.latest_run_id}`,
      { headers: { "X-Worldsim-Role": "watcher" } },
    );
    assert(apiScenes.length > 0, "advance left no scenes");
    const participant = apiScenes[apiScenes.length - 1].participant_ids[0];
    await api("/api/v1/stage2/roles/select", {
      method: "POST",
      body: JSON.stringify({
        world_id: worldId,
        role: "player",
        character_id: participant,
      }),
    });
    await page.goto(`${base}/stories/${catalog.items[0].story_id}/adventure`, {
      waitUntil: "networkidle",
    });
    await page.locator(".strip button").last().click({ timeout: 15000 });
    await page.locator("#draft").fill("dawn patrol", { timeout: 12000 });
    await page.getByRole("button", { name: "Send action" }).click({ timeout: 12000 });
    await page.locator("#queued").waitFor({ timeout: 60000 });
    const scenes = await page.locator(".strip button").count();
    assert(scenes > 0, "scene strip emptied after action");
  });

  await check("keyboard moves between scenes", async () => {
    const count = await page.locator(".strip button").count();
    if (count < 2) {
      console.log("skip: keyboard (single scene)");
      return;
    }
    await page.locator(".strip button").first().click({ timeout: 12000 });
    const first = await page.locator(".journal h1").innerText();
    await page.keyboard.press("ArrowRight");
    await page.waitForFunction(
      (before) => document.querySelector(".journal h1")?.textContent !== before,
      first,
      { timeout: 15000 },
    );
  });

  await check("action button re-enables after submit", async () => {
    await page.waitForFunction(
      () => !document.querySelector('button[aria-label="Send action"]')?.disabled,
      null,
      { timeout: 90000 },
    );
  });

  await check("wizard creates a story", async () => {
    await page.goto(`${base}/new-story`, { waitUntil: "networkidle" });
    await page.locator(".preset").first().click({ timeout: 12000 });
    await page.getByRole("button", { name: "Quick start from Ember Vale" }).click({
      timeout: 12000,
    });
    await page.getByRole("button", { name: "Create story" }).click({ timeout: 12000 });
    await page.waitForURL(/\/stories\/.*\/(adventure|world)/, { timeout: 60000 });
  });

  await check("stories catalog and setup modal", async () => {
    await page.goto(`${base}/stories`, { waitUntil: "networkidle" });
    await page.locator(".card").first().waitFor({ timeout: 15000 });
    await page.locator(".card .icon").first().click({ timeout: 12000 });
    await page.locator(".modal h2").waitFor({ timeout: 15000 });
    await page.keyboard.press("Escape");
    await page.waitForSelector(".modal", { state: "detached", timeout: 15000 });
  });

  await check("library lists split presets", async () => {
    await page.goto(`${base}/library`, { waitUntil: "networkidle" });
    const presets = await page.locator(".preset").count();
    assert(presets >= 3, "expected world plus character presets");
  });

  await check("settings loads sections", async () => {
    await page.goto(`${base}/settings`, { waitUntil: "networkidle" });
    await page.getByText("AI Providers").waitFor({ timeout: 15000 });
  });

  await check("theme selects dark", async () => {
    await page.getByRole("button", { name: "access" }).first().click({ timeout: 12000 });
    await page.locator(".settings select").selectOption("dark", { timeout: 12000 });
    const dark = await page.evaluate(() => document.documentElement.classList.contains("dark"));
    assert(dark, "dark class missing");
    await page.locator(".settings select").selectOption("light", { timeout: 12000 });
  });

  await check("clean console", async () => {
    assert(consoleErrors.length === 0, consoleErrors.slice(0, 3).join(" | "));
  });

  await check("mobile renders without overflow", async () => {
    const mobile = await browser.newPage({ viewport: { width: 390, height: 844 } });
    try {
      await mobile.goto(base, { waitUntil: "networkidle" });
      await mobile.getByRole("button", { name: /Continue Story/ }).first().waitFor({ timeout: 15000 });
      const overflow = await mobile.evaluate(() => document.documentElement.scrollWidth);
      assert(overflow <= 390, `horizontal overflow: ${overflow}`);
    } finally {
      await mobile.close();
    }
  });
} finally {
  await browser.close();
}

if (errors.length > 0) {
  console.log(`FAILED: ${errors.join(", ")}`);
  process.exit(1);
}
console.log("verify: all green");
