// Open the last Gemini image URL in a new same-browser tab (cookies apply, origin=lh3),
// then export via canvas (same-origin, not tainted). Saves PNG.
// Usage: node grab_img.mjs <outfile.png>
import { chromium } from 'playwright-core';
const out = process.argv[2];
const b = await chromium.connectOverCDP('http://127.0.0.1:9222');
const ctx = b.contexts()[0];
const gp = ctx.pages().find(p => p.url().includes('gemini.google'));
if (!gp) { console.log('no gemini page'); process.exit(1); }
const src = await gp.evaluate(() => {
  const imgs=[...document.querySelectorAll('img')].filter(e=>e.naturalWidth>300&&e.naturalHeight>300&&!/gstatic|avatar|profile|googleusercontent\/ogw/i.test(e.src));
  return imgs.length? imgs[imgs.length-1].src : null;
});
if (!src) { console.log('no image src'); process.exit(1); }
console.log('src', src.slice(0,60));
const p = await ctx.newPage();
try {
  await p.goto(src, { waitUntil: 'load', timeout: 45000 });
  await p.waitForTimeout(1500);
  const dataUrl = await p.evaluate(async () => {
    const img = document.querySelector('img');
    if (!img) return 'NOIMG';
    await img.decode().catch(()=>{});
    const c = document.createElement('canvas');
    c.width = img.naturalWidth; c.height = img.naturalHeight;
    c.getContext('2d').drawImage(img,0,0);
    return c.toDataURL('image/png');
  });
  if (!dataUrl || dataUrl==='NOIMG' || dataUrl.startsWith('ERR')) { console.log('fail', dataUrl); process.exit(2); }
  const fs = await import('fs');
  fs.writeFileSync(out, Buffer.from(dataUrl.split(',')[1],'base64'));
  console.log('SAVED', out, fs.statSync(out).size, 'bytes');
} finally { await p.close().catch(()=>{}); }
process.exit(0);
