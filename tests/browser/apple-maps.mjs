// SYNTHETIC SDK / USB boundary fixtures: never evidence of Apple service calibration.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const browser=await chromium.launch({channel:'chrome',headless:true});
const sdkFixture = `(() => {
 const target = new EventTarget();
 window.mapkit = {
  addEventListener: (...args) => target.addEventListener(...args),
  init() { const event = new Event('configuration-change'); event.status='Initialized'; queueMicrotask(()=>target.dispatchEvent(event)); },
  Map: class extends EventTarget {
   constructor(id) { super(); this.region={}; const button=document.createElement('button'); button.textContent='Synthetic map point'; button.onclick=()=>{const event=new Event('single-tap');event.pointOnPage={x:10,y:20};this.dispatchEvent(event);};document.getElementById(id).append(button); }
   convertPointOnPageToCoordinate() { return {latitude:32,longitude:122}; }
  },
  Search: class { search(query, callback) {queueMicrotask(()=>callback(null,{places:[{name:'Synthetic known point',formattedAddress:'fixture',coordinate:{latitude:31.23,longitude:121.47}}]}));} }
 };
})();`;
async function scenario(config, sdkMode='fixture') {
 const fixture=spawn(process.env.PYTHON || 'python3',['tests/fixtures/maps_server.py'],{stdio:['pipe','pipe','inherit'],env:{...process.env,LOCATION_LAB_TEST_MAPS:JSON.stringify(config)}});
 const pending=[],lines=[],reader=createInterface({input:fixture.stdout});
 reader.on('line',line=>{const value=JSON.parse(line);if(pending.length)pending.shift()(value);else lines.push(value);});
 const next=()=>lines.length ? Promise.resolve(lines.shift()) : new Promise(resolve=>pending.push(resolve));
 const command=async value=>{fixture.stdin.write(value+'\n');return next();};
 const initial=await next(),page=await browser.newPage({viewport:{width:390,height:844}});
 try {
  await page.route('https://cdn.apple-mapkit.com/mk/6/mapkit.js',route=>sdkMode==='failure' ? route.abort() : route.fulfill({contentType:'text/javascript',body:sdkFixture}));
  await page.goto(initial.pairingURL);
  await page.getByText('等待 Mac 确认',{exact:true}).waitFor();await command('approve');
  await page.getByText('配对授权已确认。可将此页面添加到主屏幕。',{exact:true}).waitFor();
  if (!config.token) {
   await page.getByText('尚未配置 Apple 地图令牌，可使用 WGS84 手工坐标。',{exact:true}).waitFor({timeout:5000});
  } else {
   await page.waitForFunction(()=>!document.querySelector('#maps-load').disabled);
   await page.getByRole('button',{name:'打开 Apple 地图',exact:true}).click();
   if (sdkMode==='failure') await page.getByText(/Apple 地图加载失败/).waitFor();
   else {
    await page.getByLabel('搜索地点').fill('synthetic');await page.getByRole('button',{name:'搜索',exact:true}).click();
    await page.getByRole('button',{name:'Synthetic known point fixture',exact:true}).click();
    assert.equal((await command('snapshot')).running,false,'selection must not apply');
    const draft=await page.evaluate(()=>window.locationLab.getDraft());
    assert.equal(draft.provider,'apple-mapkit-js');assert.equal(draft.selectionMethod,'search');
    if (config.validationEvidence) {
     assert.deepEqual(draft.normalizedWGS84,{latitude:31.23,longitude:121.47});
     await page.getByRole('button',{name:'应用位置',exact:true}).click();
     await page.waitForFunction(()=>document.querySelector('#accepted').textContent.includes('31.23, 121.47'));
     assert.equal((await command('snapshot')).status.target.provider,'apple-mapkit-js');
     await page.getByRole('button',{name:'Synthetic map point',exact:true}).click();
     assert.equal((await command('snapshot')).status.target.latitude,31.23,'map tap only changes draft');
     assert.equal((await page.evaluate(()=>window.locationLab.getDraft())).latitude,32);
    } else {
     assert.equal(draft.inputCRS,'unverified-mapkit');assert.equal(draft.normalizedWGS84,null);
     assert.equal(await page.getByRole('button',{name:'应用位置',exact:true}).isDisabled(),true);
     assert.equal(await page.getByLabel('WGS84 纬度').inputValue(),'','unknown CRS must not fill WGS84 fields');
    }
   }
  }
  await page.getByLabel('WGS84 纬度').fill('30');await page.getByLabel('WGS84 经度').fill('120');
  await page.getByRole('button',{name:'应用位置',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#accepted').textContent.includes('30, 120'));
  assert.equal((await command('snapshot')).status.target.provider,'manual');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  console.log('PASS synthetic Apple Maps scenario:',!config.token?'no-token':sdkMode==='failure'?'SDK-failure':config.validationEvidence?'explicit-local-policy':'uncalibrated');
 } finally {
  await page.close();fixture.stdin.write('quit\n');fixture.stdin.end();reader.close();
  await new Promise(resolve=>fixture.once('exit',resolve));
 }
}
try {
 await scenario({});
 await scenario({token:'synthetic.page.token'});
 await scenario({token:'synthetic.page.token',coordinatePolicy:'validated-wgs84',validationEvidence:'SYNTHETIC TEST ONLY'});
 await scenario({token:'synthetic.page.token'},'failure');
} finally {await browser.close();}
