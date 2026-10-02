"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const { spawnSync } = require("node:child_process");
const { chromium } = require(process.env.REPOPULSE_PLAYWRIGHT_MODULE || "playwright");

async function verify() {
  const output = process.argv[2] ? path.resolve(process.argv[2]) : fs.mkdtempSync(path.join(os.tmpdir(), "repopulse-browser-"));
  const result = spawnSync(process.env.REPOPULSE_PYTHON || "python", [path.join(__dirname, "create_demo.py"), "--output-dir", output], {encoding: "utf8"});
  assert.equal(result.status, 0, result.stderr);
  const browser = await chromium.launch({headless: true});
  try {
    for (const viewport of [{width: 1440, height: 1000}, {width: 390, height: 844}, {width: 320, height: 740}]) {
      const page = await browser.newPage({viewport});
      const errors = [], requests = [];
      page.on("pageerror", error => errors.push(error.message));
      page.on("console", message => {if (message.type() === "error") errors.push(message.text());});
      page.on("request", request => {if (/^https?:/.test(request.url())) requests.push(request.url());});
      await page.goto(pathToFileURL(path.join(output, "report.html")).href);
      await page.waitForFunction(() => document.getElementById("result-count").textContent !== "");
      assert.equal(await page.locator("h1").textContent(), "demo-project");
      assert.equal(await page.evaluate(() => window.pwned), undefined);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, "page overflows viewport");
      await page.locator("#severity").selectOption("error");
      assert.equal(await page.locator("#result-count").textContent(), "0 results");
      await page.locator("#severity").selectOption("warning");
      assert.ok(await page.locator("article").count() > 0);
      await page.locator("#search").fill("lockfile");
      assert.equal(await page.locator("article").count(), 1);
      await page.locator("#search").fill("");
      await page.locator("#tab-files").click();
      assert.equal(await page.locator("tbody tr").count(), 50);
      await page.locator("#next").click();
      assert.ok(await page.locator("tbody tr").count() > 0);
      assert.equal(await page.locator("#previous").isEnabled(), true);
      await page.locator("#sort").selectOption("size");
      assert.match(await page.locator("tbody tr").first().textContent(), /assets\/data.txt/);
      await page.locator("#search").fill("unsafe.py");
      const href = await page.locator("tbody a").getAttribute("href");
      assert.match(href, /^file:/);
      assert.equal(await page.locator("tbody tr").count(), 1);
      await page.locator("#search").fill("");
      await page.locator("#tab-markers").click();
      assert.ok((await page.locator("#results").textContent()).includes("globalThis.pwned=1"));
      assert.equal(await page.locator("#results script, #results img").count(), 0);
      await page.locator("#tab-changes").click();
      assert.ok((await page.locator("#results").textContent()).includes("Resolved marker"));
      assert.ok(await page.locator("#change-summary").isVisible());
      await page.locator("#tab-changes").press("Home");
      assert.equal(await page.locator("#tab-findings").getAttribute("aria-selected"), "true");
      await page.locator("#tab-findings").press("ArrowRight");
      assert.equal(await page.locator("#tab-files").getAttribute("aria-selected"), "true");
      await page.locator("#tab-findings").click();
      await page.locator("#severity").selectOption("all");
      await page.screenshot({path: path.join(output, `report-${viewport.width}.png`), fullPage: true});
      await page.goto(pathToFileURL(path.join(output, "no-baseline.html")).href);
      await page.locator("#tab-changes").click();
      assert.match(await page.locator("#results").textContent(), /No baseline supplied/);
      await page.goto(pathToFileURL(path.join(output, "empty.html")).href);
      assert.equal(await page.locator("#score").textContent(), "Not scored");
      assert.equal(await page.locator("#result-count").textContent(), "0 results");
      await page.locator("#tab-files").click();
      assert.match(await page.locator("#results").textContent(), /No items/);
      assert.deepEqual(errors, [], "browser errors");
      assert.deepEqual(requests, [], "report made network requests");
      await page.close();
    }
  } finally {
    await browser.close();
  }
  console.log("Browser checks passed at 1440, 390, and 320 pixels: filtering, pagination, source links, comparisons, keyboard tabs, empty states, injection protection, no network requests.");
  console.log("Screenshots: " + output);
}

verify().catch(error => {console.error(error); process.exitCode = 1;});
