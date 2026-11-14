const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const url = process.argv[2] || 'http://localhost:8077/';
  const out = process.argv[3] || '/tmp/shot';
  for (const [name, vp] of [['desk', {width: 1440, height: 900}], ['phone', {width: 390, height: 844}]]) {
    const p = await b.newPage({viewport: vp, deviceScaleFactor: 1});
    p.on('pageerror', e => console.log('PAGEERROR', e.message));
    await p.goto(url); await p.waitForTimeout(800);
    await p.screenshot({path: `${out}-${name}-0.png`});
    if (name === 'desk') {
      await p.click('#plan-btn');
      await p.waitForSelector('#result:not(.hidden)', {timeout: 180000});
      await p.waitForTimeout(500);
      await p.screenshot({path: `${out}-${name}-1.png`, fullPage: true});
      await p.click('.dfoot .btn'); await p.waitForTimeout(1500);
      await p.click('.tab[data-view=audit]'); await p.waitForTimeout(300);
      await p.screenshot({path: `${out}-${name}-2.png`});
      await p.click('.tab[data-view=agents]'); await p.waitForTimeout(300);
      await p.screenshot({path: `${out}-${name}-3.png`});
    }
  }
  await b.close();
})();
