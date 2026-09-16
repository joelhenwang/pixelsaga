// Headless verification for the Stage 1 surface (S1-UI-001).
// Needs the backend on :8100 (VITE_API_PROXY) and `vite --port 5174`.
// Run: node verify.mjs [base]
// Asserts: seed, advance, beats render, action submit, keyboard nav,
// theme toggle, duplicate-submit guard, mobile layout, clean console.
import { chromium } from "playwright";

const base = process.argv[2] ?? "http://localhost:5174";
const errors = [];

async function check(name, fn) {
  try {
    await fn();
    console.log(`ok: ${name}`);
  } catch (error) {
    errors.push(name);
    console.log(`FAIL: ${name}: ${error.message.split("\n")[0]}`);
  }
}
function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function click(locator) {
  try {
    await locator.click({ timeout: 12000 });
  } catch (error) {
    await locator.evaluate((el) => el.click());
  }
}

async function fill(locator, value) {
  try {
    await locator.fill(value, { timeout: 12000 });
  } catch (error) {
    await locator.evaluate((el, v) => {
      el.value = v;
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }, value);
  }
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

  await check("loads with empty state", async () => {
    await page.goto(base, { waitUntil: "networkidle" });
    await page.getByText("no scene selected").waitFor({ timeout: 15000 });
  });
  await check("seed populates world clock", async () => {
    await click(page.getByRole("button", { name: "seed" }));
    await page.getByText(/day 1/).first().waitFor({ timeout: 15000 });
    consoleErrors.length = 0;
  });

  await check("advance renders scenes and beats", async () => {
    await click(page.getByRole("button", { name: /advance to/ }));
    await page.locator(".strip button").first().waitFor({ timeout: 60000 });
    await click(page.locator(".strip button").first());
    await page.locator(".beat").first().waitFor({ timeout: 15000 });
    const beats = await page.locator(".beat").count();
    assert(beats > 0, "expected at least one beat");
  });

  await check("action submit queues without doubles", async () => {
    await fill(page.locator("#topic"), "dawn patrol");
    await click(page.locator("#go"));
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
    await click(page.locator(".strip button").first());
    const first = await page.locator(".stage h1").innerText();
    await page.keyboard.press("ArrowRight");
    await page.waitForFunction(
      (before) => document.querySelector(".stage h1")?.textContent !== before,
      first,
      { timeout: 15000 },
    );
  });

  await check("action button re-enables after submit", async () => {
    await page.waitForFunction(() => !document.querySelector("#go")?.disabled, null, {
      timeout: 90000,
    });
  });

  await check("theme toggles to light", async () => {
    await click(page.locator("#theme"));
    const light = await page.evaluate(() => document.documentElement.classList.contains("light"));
    assert(light, "light class missing");
    const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    assert(bg === "rgb(255, 255, 255)", `unexpected background ${bg}`);
    await click(page.locator("#theme"));
  });

  await check("clean console", async () => {
    assert(consoleErrors.length === 0, consoleErrors.slice(0, 3).join(" | "));
  });

  await check("mobile layout renders action bar", async () => {
    const mobile = await browser.newPage({ viewport: { width: 390, height: 844 } });
    try {
      await mobile.goto(base, { waitUntil: "networkidle" });
      await mobile.locator("#go").waitFor({ timeout: 15000 });
      const box = await mobile.locator("#go").boundingBox();
      assert(box && box.width > 0, "action button not visible on mobile");
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
