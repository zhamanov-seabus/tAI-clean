// Drive Gemini web (controlled Chrome :9222) to generate an image, then extract it.
// Usage: node gemini-image.mjs "<prompt>" <outfile.png>
const prompt = process.argv[2];
const out = process.argv[3] || '/tmp/gemini-out.png';

async function conn() {
  const list = await (await fetch('http://127.0.0.1:9222/json')).json();
  const t = list.find(x => x.type === 'page' && x.url.includes('gemini.google'));
  if (!t) throw new Error('no gemini page');
  const ws = new WebSocket(t.webSocketDebuggerUrl);
  let id = 0; const pending = new Map();
  ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && pending.has(d.id)) { const p = pending.get(d.id); pending.delete(d.id); d.error ? p.rej(new Error(JSON.stringify(d.error))) : p.res(d.result); } };
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = () => rej(new Error('ws err')); });
  const send = (method, params = {}) => new Promise((res, rej) => { const mid = ++id; pending.set(mid, { res, rej }); ws.send(JSON.stringify({ id: mid, method, params })); });
  await send('Runtime.enable'); await send('Page.enable').catch(()=>{});
  return { ws, send };
}
const sleep = ms => new Promise(r => setTimeout(r, ms));
const evalJS = async (send, expr, awaitPromise=false) => {
  const r = await send('Runtime.evaluate', { expression: `(function(){ try { return (${expr}); } catch(e){ return 'ERR:'+e.message; } })()`, returnByValue: true, awaitPromise });
  return r.result && r.result.value;
};
const imgcount = send => evalJS(send, `[...document.querySelectorAll('img')].filter(e=>e.naturalWidth>300&&e.naturalHeight>300&&!/gstatic|avatar|profile|googleusercontent\\/ogw/i.test(e.src)).length`);

const { ws, send } = await conn();
try {
  // fresh chat
  await send('Page.navigate', { url: 'https://gemini.google.com/app' });
  await sleep(5000);
  const loggedIn = await evalJS(send, `!!document.querySelector('div[contenteditable="true"], rich-textarea .ql-editor, textarea')`);
  console.log('input-present', loggedIn, '| title', await evalJS(send,'document.title'));
  if (!loggedIn) { console.log('NOT-LOGGED-IN-OR-NO-INPUT'); process.exit(2); }
  const before = await imgcount(send);
  // focus + type
  await evalJS(send, `(()=>{const el=document.querySelector('div[contenteditable="true"], rich-textarea .ql-editor, textarea'); if(el){el.focus();return 1;}return 0;})()`);
  await sleep(400);
  await send('Input.insertText', { text: prompt });
  await sleep(800);
  // submit: click send button, fallback Enter
  const clicked = await evalJS(send, `(()=>{const b=[...document.querySelectorAll('button')].find(x=>/send/i.test(x.getAttribute('aria-label')||'')||/send/i.test(x.getAttribute('mattooltip')||'')); if(b){b.click();return 'clicked';}return 'nobtn';})()`);
  console.log('submit', clicked);
  if (clicked === 'nobtn') {
    await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,nativeVirtualKeyCode:13});
    await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,nativeVirtualKeyCode:13});
  }
  // poll for a new image up to 180s
  let got=false;
  for (let i=0;i<60;i++){
    await sleep(3000);
    const n = await imgcount(send);
    if (i%4===0) console.log('t='+(i*3)+'s imgs='+n);
    if (n>before){ got=true; await sleep(4000); break; }
  }
  if(!got){ console.log('NO-NEW-IMAGE'); process.exit(3); }
  const fs = await import('fs');
  const dataUrl = await evalJS(send, `(()=>{const imgs=[...document.querySelectorAll('img')].filter(e=>e.naturalWidth>300&&e.naturalHeight>300&&!/gstatic|avatar|profile|googleusercontent\\/ogw/i.test(e.src)); if(!imgs.length) return 'NONE'; const img=imgs[imgs.length-1]; const c=document.createElement('canvas'); c.width=img.naturalWidth; c.height=img.naturalHeight; c.getContext('2d').drawImage(img,0,0); return c.toDataURL('image/png');})()`);
  if (!dataUrl || dataUrl==='NONE' || dataUrl.startsWith('ERR')){ console.log('extract-fail',dataUrl); process.exit(4); }
  fs.writeFileSync(out, Buffer.from(dataUrl.split(',')[1],'base64'));
  console.log('SAVED', out, fs.statSync(out).size,'bytes');
} catch(e){ console.error('ERR', e.message); process.exit(1); }
finally { ws.close(); }
process.exit(0);
