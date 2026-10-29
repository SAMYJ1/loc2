'use strict';
const el = id => document.getElementById(id);
const report = { schemaVersion: 1, tool: 'mapkit-validation', origin: location.origin, userAgent: navigator.userAgent, startedAt: new Date().toISOString(), liveMapVerification: 'unverified', coordinateCalibration: 'unverified', usbSessionStarted: false, observations: [], events: [] };
const render = () => { el('report').textContent = JSON.stringify(report, null, 2); };
const message = text => { el('message').textContent = text; };
function coordinate(lat, lon) {
  if (String(lat).trim() === '' || String(lon).trim() === '') throw new Error('请填写完整坐标。');
  const latitude = Number(lat), longitude = Number(lon);
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude) || Math.abs(latitude) > 90 || Math.abs(longitude) > 180) throw new Error('坐标必须有限，纬度在 ±90、经度在 ±180 范围内。');
  return { latitude, longitude };
}
function record(inputCoordinate, provider, method, name = '') {
  report.observations.push({ id: report.observations.length + 1, recordedAt: new Date().toISOString(), provider, method, name, inputCoordinate, inputCRS: provider === 'manual' ? 'WGS84' : 'unverified-mapkit', normalizedWGS84: provider === 'manual' ? inputCoordinate : null, referenceWGS84: null });
  render(); message('已记录选点草稿，未应用位置。');
}
el('manual').addEventListener('submit', event => {
  event.preventDefault();
  try { record(coordinate(el('latitude').value, el('longitude').value), 'manual', 'coordinate-input'); }
  catch (error) { message(error.message); }
});
el('reference').addEventListener('submit', event => {
  event.preventDefault();
  try {
    const observation = [...report.observations].reverse().find(item => item.provider === 'apple-mapkit-js');
    if (!observation) throw new Error('请先搜索或点选一个地图点。');
    const source = el('reference-source').value.trim();
    if (!source) throw new Error('请填写独立参照的来源。');
    observation.referenceWGS84 = { ...coordinate(el('reference-latitude').value, el('reference-longitude').value), source };
    render(); message('已记录独立参照；仍需评估偏差，未自动归一化地图坐标。');
  } catch (error) { message(error.message); }
});
el('export').addEventListener('click', () => {
  const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }));
  const a = document.createElement('a'); a.href = url; a.download = 'location-lab-map-observations.json'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
render();
let map;
let mapFailed = false;
let searchSequence = 0;
const event = kind => { report.events.push({ kind, at: new Date().toISOString() }); render(); };
const mapStatus = text => { el('map-status').textContent = text; };
function mapError(kind) {
  mapFailed = true; searchSequence++;
  el('search-button').disabled = true; el('confirm-map').disabled = true;
  mapStatus('地图加载或服务失败；手工 WGS84 仍可使用。检查令牌、网络与原点限制后刷新重试。');
  event(kind);
}
el('load').addEventListener('click', async () => {
  let token = el('token').value.trim();
  if (!token) { mapStatus('缺少 Maps token；手工 WGS84 仍可使用。'); return; }
  el('token').value = ''; el('token').disabled = true; el('load').disabled = true;
  mapStatus('正在加载 Apple 地图；初始化完成不等于底图已显示。');
  try {
    await new Promise((resolve, reject) => {
      const script = document.createElement('script');
      const timer = setTimeout(() => { script.remove(); reject(new Error('timeout')); }, 20000);
      script.src = 'https://cdn.apple-mapkit.com/mk/6/mapkit.js'; script.crossOrigin = 'anonymous';
      script.onload = () => { clearTimeout(timer); resolve(); };
      script.onerror = () => { clearTimeout(timer); reject(new Error('load')); };
      document.head.appendChild(script);
    });
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('timeout')), 20000);
      mapkit.addEventListener('configuration-change', e => {
        if (e.status === 'Initialized' || e.status === 'Refreshed') { clearTimeout(timer); resolve(); }
      });
      mapkit.addEventListener('error', () => { clearTimeout(timer); mapError('mapkit-error'); reject(new Error('authorization')); });
      mapkit.init({ authorizationCallback: done => done(token), language: 'zh-Hans' });
    });
    if (mapFailed) return;
    map = new mapkit.Map('map');
    report.mapkitVersion = mapkit.version || 'unknown';
    map.addEventListener('single-tap', e => {
      if (mapFailed) return;
      try {
        const c = map.convertPointOnPageToCoordinate(e.pointOnPage);
        record(coordinate(c.latitude, c.longitude), 'apple-mapkit-js', 'map-tap');
      } catch { message('无法记录这个地图点，请重试。'); }
    });
    el('search-button').disabled = false; el('confirm-map').disabled = false;
    event('mapkit-initialized');
    mapStatus('MapKit 已初始化。请观察底图是否正常显示并记录；坐标校准仍待完成。');
  } catch { token = ''; if (!mapFailed) mapError('mapkit-load-failed'); }
});
el('confirm-map').addEventListener('click', () => {
  report.liveMapVerification = 'user-observed-basemap'; event('user-observed-basemap');
  mapStatus('已记录人工观察到底图；这不证明搜索、坐标校准或 USB 位置采用。');
});
el('search').addEventListener('submit', e => {
  e.preventDefault();
  const query = el('query').value.trim();
  if (!map || mapFailed || !query) return;
  const sequence = ++searchSequence;
  el('results').replaceChildren(); mapStatus('正在搜索…');
  const search = new mapkit.Search({ region: map.region });
  try {
    const pending = search.search(query, (error, data) => {
      if (sequence !== searchSequence || mapFailed) return;
      if (error) { mapStatus('搜索失败；手工 WGS84 仍可使用。'); event('search-failed'); return; }
      const places = data.places || [];
      mapStatus(`搜索返回 ${places.length} 个结果；选择结果以记录坐标。`); event('search-completed');
      for (const place of places) {
        const li = document.createElement('li'), button = document.createElement('button');
        button.textContent = `${place.name || '未命名地点'} ${place.formattedAddress || ''}`;
        button.addEventListener('click', () => {
          try {
            record(coordinate(place.coordinate.latitude, place.coordinate.longitude), 'apple-mapkit-js', 'search', place.name || '');
            map.center = place.coordinate;
          } catch { message('搜索结果坐标无效，未记录。'); }
        });
        li.appendChild(button); el('results').appendChild(li);
      }
    });
    if (pending && typeof pending.catch === 'function') pending.catch(() => {}); // Callback owns the visible outcome.
  } catch { mapStatus('搜索不可用；手工 WGS84 仍可使用。'); event('search-failed'); }
});
