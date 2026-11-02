import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const directory=await mkdtemp(join(tmpdir(),'loc2-auth-'));
async function start(port=0) {
  const child=spawn(process.env.PYTHON || 'python3',['tests/fixtures/persistent_phone_server.py','--state-dir',directory,'--port',String(port)],{stdio:['pipe','pipe','inherit']});
  const pending=[],lines=[];
  const reader=createInterface({input:child.stdout});
  reader.on('line',line=>{const value=JSON.parse(line);if(pending.length)pending.shift()(value);else lines.push(value);});
  const next=()=>lines.length?Promise.resolve(lines.shift()):new Promise(resolve=>pending.push(resolve));
  const ready=await next();
  return {ready,command:async value=>{child.stdin.write(value+'\n');return next();},close:async()=>{
    const done=new Promise(resolve=>child.once('exit',resolve));child.stdin.write('quit\n');child.stdin.end();await done;reader.close();
  }};
}
let fixture=await start();
const browser=await chromium.launch({channel:'chrome',headless:true});
let context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
try {
  let page=await context.newPage();
  await page.goto(fixture.ready.pairingURL);
  await page.getByText('等待 Mac 确认',{exact:true}).waitFor();await fixture.command('approve');
  await page.getByText('配对授权已确认。可将此页面添加到主屏幕。',{exact:true}).waitFor();
  const cookie=(await context.cookies()).find(item=>item.name==='loc2_control');
  assert.ok(cookie.expires>Date.now()/1000+86400);
  await page.getByLabel('WGS84 纬度').fill('31.23');await page.getByLabel('WGS84 经度').fill('121.47');
  await page.getByRole('button',{name:'应用位置',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#connection').textContent.includes('正在报点'));
  await context.setOffline(true);
  await page.waitForFunction(()=>document.querySelector('#connection').textContent.includes('无法连接 Mac'));
  assert.equal((await fixture.command('snapshot')).running,true);
  await context.setOffline(false);
  const saved=await context.storageState();const original=(await fixture.command('snapshot')).status;
  await context.close();assert.equal((await fixture.command('snapshot')).running,true);
  const port=fixture.ready.port;await fixture.close();fixture=await start(port);
  context=await browser.newContext({storageState:saved,viewport:{width:390,height:844},isMobile:true,hasTouch:true});
  page=await context.newPage();await page.goto(fixture.ready.origin);
  await page.getByText('配对授权已确认。可将此页面添加到主屏幕。',{exact:true}).waitFor();
  const restarted=await fixture.command('snapshot');assert.equal(restarted.running,false);assert.equal(restarted.status.target,null);
  assert.notEqual(restarted.status.controlEpoch,original.controlEpoch);
  await fixture.command('revoke');
  await page.getByText('尚未获得配对授权',{exact:true}).waitFor();
  assert.equal(await page.getByRole('button',{name:'应用位置',exact:true}).isDisabled(),true);
  assert.equal((await context.cookies()).some(item=>item.name==='loc2_control'),false);
  const repair=await fixture.command('pair');await page.goto(repair.phone.pairingURL);
  await page.getByText('等待 Mac 确认',{exact:true}).waitFor();await fixture.command('approve');
  await page.getByText('配对授权已确认。可将此页面添加到主屏幕。',{exact:true}).waitFor();
  console.log('PASS persistent cookie + browser/host restart + no session replay + offline/page-close continuity + local revoke + re-pair');
} finally {
  await browser.close();await fixture.close();await rm(directory,{recursive:true,force:true});
}
