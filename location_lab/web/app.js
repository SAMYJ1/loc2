'use strict';
const $ = id => document.getElementById(id);
let state = null, draft = null, busy = false, reachable = false, pairing = null;
function randomHex() {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, value => value.toString(16).padStart(2,'0')).join('');
}
async function request(path, body) {
  const response = await fetch(path, { method:body ? 'POST':'GET', credentials:'same-origin', cache:'no-store',
    headers:body ? {'Content-Type':'application/json'}:{}, body:body ? JSON.stringify(body):undefined });
  const result = await response.json();
  if (!response.ok) { const error = new Error(result.error || '请求失败'); error.status = response.status; throw error; }
  return result;
}
function getState() { return state ? structuredClone(state) : null; }
function getDraft() { return draft ? structuredClone(draft) : null; }
function setDraft(point) {
  draft = point ? structuredClone(point) : null;
  if (point) { $('latitude').value = point.latitude ?? ''; $('longitude').value = point.longitude ?? ''; }
  $('draft-status').textContent = point ? '草稿已更新，点击应用后才改变目标位置。':'请输入有效的 WGS84 经纬度。';
  render(); window.dispatchEvent(new CustomEvent('locationlab:draft',{detail:getDraft()}));
}
function manualDraft() {
  const latitude = Number($('latitude').value), longitude = Number($('longitude').value);
  if (!$('latitude').value.trim() || !$('longitude').value.trim() || !Number.isFinite(latitude) || !Number.isFinite(longitude) || Math.abs(latitude)>90 || Math.abs(longitude)>180) { setDraft(null);return; }
  setDraft({latitude,longitude,inputCRS:'WGS84',provider:'manual',inputCoordinate:{latitude,longitude},normalizedWGS84:{latitude,longitude}});
}
function render() {
  const s = state?.status;
  $('apply').disabled = busy || !reachable || !draft || !s || !s.availableDevices.includes(state.deviceId);
  $('stop').disabled = busy || !reachable || !s?.sessionId;
  if (!state) return;
  const names = {ready:'USB 已就绪',disconnected:'USB 未连接',connecting:'目标已接受，USB 正在连接', 'waiting-for-subscription':'USB 已连接，等待手机订阅',reporting:'正在报点',stopped:'已停止报点',error:'USB 会话异常'};
  $('connection').textContent = reachable ? `Mac 已连接 · ${names[s.state] || s.state}`:'无法连接 Mac，请检查同网连接；可在 Mac 菜单栏停止报点。';
  $('pairing').textContent = '配对授权已确认。可将此页面添加到主屏幕。';
  $('device').textContent = `授权目标手机：${state.deviceId}`;
  $('accepted').textContent = s.target ? `已接受目标：${s.target.latitude}, ${s.target.longitude} · WGS84`:'尚未应用目标位置';
  $('evidence').textContent = s.adoption === 'user-confirmed' ? '位置采用：用户已确认':'位置采用：未确认；本地报点不代表手机已采用。';
  $('recovery').textContent = s.recovery === 'user-confirmed' ? '恢复真实位置：用户已确认' : s.recovery === 'pending' ? '恢复真实位置：待手机单独确认；必要时手动关闭再开启定位服务。':'停止后，请在手机地图中单独确认真实位置恢复。';
}
async function refresh() {
  try {
    if (pairing) {
      const result = await request('/api/pair/poll', pairing);
      if (result.state === 'pending') return;
      pairing = null; sessionStorage.removeItem('location-lab-pending');
    }
    state = await request('/api/status');reachable = true;render();
    window.dispatchEvent(new CustomEvent('locationlab:status',{detail:getState()}));
  } catch (error) {
    reachable = false;
    if (error.status === 401) { state = null;$('connection').textContent = '尚未获得配对授权';$('pairing').textContent = '请在 Mac 生成二维码，扫描后由 Mac 确认。'; }
    else if (pairing && error.status === 403) { pairing = null;sessionStorage.removeItem('location-lab-pending');$('pairing').textContent = error.message; }
    else if (error.status === 403) { state = null;$('connection').textContent = '授权目标当前不可用';$('pairing').textContent = error.message; }
    else if (!state) $('connection').textContent = '无法连接 Mac，请检查两端网络。';
    render();
  }
}
async function command(action) {
  if (!state || busy || !reachable) return;
  busy = true;render();$('feedback').textContent = '';
  try {
    state = await request('/api/'+action,{deviceId:state.deviceId,point:getDraft(),requestId:randomHex(),timestamp:Date.now()/1000,expectedRevision:state.status.controlRevision,expectedEpoch:state.status.controlEpoch});
    $('feedback').textContent = action === 'apply' ? '目标已接受，请在手机地图中确认位置采用。':'已停止报点，请单独确认真实位置恢复。';
  } catch (error) { $('feedback').textContent = error.message; }
  finally { busy = false;await refresh();render(); }
}
async function begin() {
  const fragment = new URLSearchParams(location.hash.slice(1)), challenge = fragment.get('pair');
  if (challenge) history.replaceState(null,'',location.pathname);
  try {
    if (challenge) {
      const pollSecret = randomHex();
      const result = await request('/api/pair/request',{challenge,pollSecret,label:'手机浏览器'});
      pairing = {requestId:result.requestId,pollSecret};
      sessionStorage.setItem('location-lab-pending',JSON.stringify(pairing));
    } else {
      const saved = sessionStorage.getItem('location-lab-pending');
      if (saved) pairing = JSON.parse(saved);
    }
    if (pairing) { $('connection').textContent='等待 Mac 确认';$('pairing').textContent='请在 Mac 核对控制端请求和目标 USB 手机，点击允许。'; }
  } catch (error) { $('pairing').textContent = error.message; }
  await refresh(); setInterval(refresh,1500);
}
$('latitude').addEventListener('input',manualDraft);$('longitude').addEventListener('input',manualDraft);
$('apply').addEventListener('click',()=>command('apply'));$('stop').addEventListener('click',()=>command('stop'));
window.locationLab = {setDraft,getDraft,request,getState};
begin();
