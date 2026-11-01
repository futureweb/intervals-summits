// Opens a summit log page in headless Chromium: no script errors, the parts filled, hover and pin work.
//   node tests/browser_check.js page.html
// Needs playwright (npm install playwright && npx playwright install chromium), or set
// PLAYWRIGHT_CORE to a playwright-core directory and CHROMIUM to a Chromium binary.
const path = require('path');
const resolve = () => {
  for (const m of [process.env.PLAYWRIGHT_CORE, 'playwright', 'playwright-core'].filter(Boolean)) {
    try { return require.resolve(m, { paths: [process.cwd(), __dirname] }); } catch (e) { /* next */ }
  }
  console.log('playwright not found'); process.exit(2);
};
const { chromium } = require(resolve());
(async () => {
  const opts = { args: ['--no-sandbox'] };
  if (process.env.CHROMIUM) opts.executablePath = process.env.CHROMIUM;
  const b = await chromium.launch(opts);
  const p = await b.newPage({ viewport: { width: 1200, height: 1000 } });
  const errors = [];
  p.on('pageerror', e => errors.push(String(e)));
  await p.goto('file://' + path.resolve(process.argv[2]));
  const kpi = (await p.locator('#kpis .kpi').first().innerText()).replace(/\s+/g, ' ');
  console.log('kpis=' + kpi, 'rows=' + await p.locator('#rows tr').count(), 'top=' + await p.locator('#topbars .b').count());
  await p.locator('#scatter svg').scrollIntoViewIfNeeded();          // the map card above may push it down
  const c = await p.evaluate(() => { const q = SP[0]; const r = document.querySelector('#scatter svg').getBoundingClientRect(), k = r.width / 1000; return { x: r.left + q.x * k, y: r.top + q.y * k }; });
  await p.mouse.move(c.x + 2, c.y + 2);
  const hover = await p.locator('#tip').isVisible();
  await p.mouse.click(c.x + 2, c.y + 2);
  const href = await p.locator('#tip a').getAttribute('href');
  console.log('hover=' + hover, 'link=' + href);
  // the map loads once it is in view: drawn with Leaflet, or (offline) the hint instead – never an error
  await p.locator('#map').scrollIntoViewIfNeeded();
  let map = 'none';
  for (let i = 0; i < 40 && map === 'none'; i++) {
    await p.waitForTimeout(250);
    map = await p.evaluate(() => document.querySelector('#map .leaflet-marker-pane') ? 'leaflet'
      : /internet/i.test(document.getElementById('map').textContent) ? 'offline' : 'none');
  }
  const markers = await p.locator('#map path.leaflet-interactive').count();
  console.log('map=' + map, 'markers=' + markers, 'collections=' + await p.locator('#colls .b').count());
  if (map === 'none') errors.push('the map neither drew nor said why');
  if (process.env.SCREENSHOT) await p.screenshot({ path: process.env.SCREENSHOT, fullPage: true });
  await b.close();
  if (errors.length || !hover || !href) { console.log('errors=' + JSON.stringify(errors)); process.exit(1); }
})();
