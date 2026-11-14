/* Every automated writer gets an isolated kitchen, including outside MCP clients. */
const { randomUUID } = require("node:crypto");
module.exports = function testKitchen() {
  const run = process.env.VALIO_TEST_RUN || randomUUID().replaceAll("-", "");
  if (!/^[a-f0-9]{32}$/.test(run))
    throw new Error("Invalid test kitchen run ID");
  return { run, headers: { "x-valio-test-run": run } };
};
