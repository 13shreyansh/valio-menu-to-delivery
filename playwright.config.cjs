const { defineConfig } = require("@playwright/test");
module.exports = defineConfig({
  testDir: "./tests",
  testMatch: "portal.e2e.cjs",
  workers: 1,
  reporter: [["list"], ["json", { outputFile: "artifacts/e2e/results.json" }]],
  use: { headless: true, trace: "retain-on-failure" },
  outputDir: "artifacts/e2e/traces",
});
