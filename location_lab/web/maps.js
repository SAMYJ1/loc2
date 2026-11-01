/* Apple Maps is an optional selection source; applying remains an explicit shared action. */
(() => {
  'use strict';
  const nonce = document.currentScript.nonce;
  const lab = window.locationLab;
  const root = document.createElement('section');
  root.className = 'map-tools';
  root.innerHTML = `<h3>Apple 地图</h3><p id="maps-status" class="secondary" role="status">配对后可使用 Apple 地图。</p><button id="maps-load" type="button" class="secondary-button" disabled>打开 Apple 地图</button><div id="apple-map" hidden></div><form id="maps-search" hidden><label>搜索地点<input id="maps-query" autocomplete="off" maxlength="200" required></label><button id="maps-search-button" type="submit">搜索</button></form><ul id="maps-results"></ul>`;
  document.getElementById('selection-tools').append(root);
  const $ = id => document.getElementById(id);
  let settings = null, map = null, loading = false, failed = false, configPending = false, configLoaded = false, searchSequence = 0;
  const status = message => { $('maps-status').textContent = message; };
  const policyNote = () => settings?.canApplyMapPoints ? '已配置本机 WGS84 校准策略。选点后仍需明确应用。' : '地图坐标尚未校准；可查看草稿，应用请使用手工 WGS84。';
  function fail(message) {
    failed = true; searchSequence++; $('maps-search-button').disabled = true;
    status(message + ' 手工 WGS84 输入仍可使用；检查本机配置后刷新页面重试。');
  }
  async function config() {
    if (!lab.getState() || configPending || configLoaded) return;
    configPending = true;
    try {
      settings = await lab.request('/api/maps-config'); configLoaded = true;
      lab.setMapPolicy(settings.canApplyMapPoints);
      $('maps-load').disabled = !settings.token;
      status(settings.token ? policyNote() : '尚未配置 Apple 地图令牌，可使用 WGS84 手工坐标。');
    } catch { status('无法读取地图配置；手工 WGS84 输入仍可使用。'); }
    finally { configPending = false; }
  }
  function draft(c, method) {
    const latitude = c?.latitude, longitude = c?.longitude;
    if (typeof latitude !== 'number' || typeof longitude !== 'number' || !Number.isFinite(latitude) || !Number.isFinite(longitude) || Math.abs(latitude)>90 || Math.abs(longitude)>180) { status('地图坐标无效，请重新选点。'); return; }
    const inputCoordinate = {latitude,longitude};
    lab.setDraft({latitude,longitude,provider:'apple-mapkit-js',selectionMethod:method,inputCoordinate,inputCRS:settings.canApplyMapPoints ? 'WGS84':'unverified-mapkit',normalizedWGS84:settings.canApplyMapPoints ? {...inputCoordinate}:null});
    status(policyNote());
  }
  $('maps-load').addEventListener('click', async () => {
    if (!settings?.token || loading || map) return;
    loading = true; $('maps-load').disabled = true; status('正在加载 Apple 地图…');
    try {
      await new Promise((resolve,reject) => {
        const script = document.createElement('script'), timer = setTimeout(() => { script.remove(); reject(); },20000);
        script.src = 'https://cdn.apple-mapkit.com/mk/6/mapkit.js'; script.crossOrigin = 'anonymous'; script.nonce = nonce;
        script.onload = () => { clearTimeout(timer); resolve(); };
        script.onerror = () => { clearTimeout(timer); reject(); };
        document.head.append(script);
      });
      await new Promise((resolve,reject) => {
        const timer = setTimeout(reject,20000);
        mapkit.addEventListener('configuration-change', event => {
          if (event.status === 'Initialized' || event.status === 'Refreshed') { clearTimeout(timer); resolve(); }
        });
        mapkit.addEventListener('error', () => { clearTimeout(timer); fail('Apple 地图授权或服务不可用。'); reject(); });
        mapkit.init({ authorizationCallback: done => done(settings.token), language:'zh-Hans' });
      });
      if (failed) return;
      $('apple-map').hidden = false; map = new mapkit.Map('apple-map');
      map.addEventListener('single-tap', event => { if (!failed) draft(map.convertPointOnPageToCoordinate(event.pointOnPage),'map-tap'); });
      $('maps-search').hidden = false; status(policyNote());
    } catch { if (!failed) fail('Apple 地图加载失败。'); }
  });
  $('maps-search').addEventListener('submit', event => {
    event.preventDefault();
    const query = $('maps-query').value.trim();
    if (!map || failed || !query) return;
    const sequence = ++searchSequence;
    $('maps-results').replaceChildren(); status('正在搜索…');
    const timer = setTimeout(() => { if (sequence === searchSequence) { searchSequence++; status('搜索超时，请重试；手工 WGS84 输入仍可使用。'); } },20000);
    try {
      const pending = new mapkit.Search({region:map.region}).search(query,(error,data) => {
        clearTimeout(timer);
        if (sequence !== searchSequence || failed) return;
        if (error) { status('搜索失败，请重试；手工 WGS84 输入仍可使用。'); return; }
        const places = data?.places || []; status(places.length ? '选择搜索结果以更新草稿。' : '没有找到地点，请调整搜索内容。');
        for (const place of places) {
          const item = document.createElement('li'), button = document.createElement('button');
          button.className = 'secondary-button'; button.type = 'button'; button.textContent = `${place.name || '未命名地点'} ${place.formattedAddress || ''}`;
          button.addEventListener('click', () => { if (!failed) { draft(place.coordinate,'search'); map.center = place.coordinate; } });
          item.append(button); $('maps-results').append(item);
        }
      });
      if (pending?.catch) pending.catch(() => {});
    } catch { clearTimeout(timer); status('搜索不可用；手工 WGS84 输入仍可使用。'); }
  });
  window.addEventListener('locationlab:status', config);
  config();
})();
