/* Favorites live on the Mac. Selecting one only updates the draft. */
(() => {
  'use strict';
  const api = window.loc2;
  const container = document.createElement('section');
  container.className = 'favorites';
  container.innerHTML = '<h3>常用点</h3><p class="secondary">保存在 Mac，选择后仍需明确应用。</p><label>收藏名称<input id="favorite-name" maxlength="80" placeholder="为当前草稿命名"></label><button id="favorite-save" class="secondary-button" disabled>收藏当前草稿</button><p id="favorite-message" class="secondary" role="status"></p><ul id="favorite-list"></ul>';
  document.getElementById('selection-tools').append(container);
  const name = container.querySelector('#favorite-name');
  const save = container.querySelector('#favorite-save');
  const list = container.querySelector('#favorite-list');
  const message = container.querySelector('#favorite-message');
  let busy = false, loading = false, loadedDevice = null;
  function updateSave() { save.disabled = busy || !api.getState() || !api.getDraft() || !name.value.trim(); }
  function render(items) {
    list.replaceChildren();
    if (!items.length) { const item = document.createElement('li');item.textContent = '还没有常用点。';item.className = 'secondary';list.append(item);return; }
    for (const favorite of items) {
      const item = document.createElement('li');
      const choose = document.createElement('button');choose.className = 'favorite-choice secondary-button';choose.textContent = favorite.name;choose.setAttribute('aria-label','选择 '+favorite.name);
      const coordinates = document.createElement('span');coordinates.className = 'secondary';coordinates.textContent = `${favorite.point.latitude}, ${favorite.point.longitude} · ${favorite.point.inputCRS === 'WGS84' ? 'WGS84':'待校准'}`;
      choose.append(coordinates);
      choose.addEventListener('click',()=>{api.setDraft(favorite.point);message.textContent = '已载入收藏草稿；点击应用后才改变目标。';});
      const remove = document.createElement('button');remove.className = 'favorite-remove secondary-button';remove.textContent = '删除';remove.setAttribute('aria-label','删除 '+favorite.name);
      remove.addEventListener('click',()=>mutate('remove',{favoriteId:favorite.id}));
      item.append(choose,remove);list.append(item);
    }
  }
  async function load(force = false) {
    const state = api.getState();updateSave();
    if (!state) { list.replaceChildren();loadedDevice = null;return; }
    if (loading || (!force && loadedDevice === state.deviceId)) return;
    loading = true;
    try { const result = await api.request('/api/favorites');loadedDevice = state.deviceId;render(result.favorites); }
    catch (error) { message.textContent = error.message;if (error.status === 401 || error.status === 403) { list.replaceChildren();loadedDevice = null; } }
    finally { loading = false; }
  }
  function requestId() { const bytes = new Uint8Array(32);crypto.getRandomValues(bytes);return Array.from(bytes,n=>n.toString(16).padStart(2,'0')).join(''); }
  async function mutate(action, body) {
    const state = api.getState();if (!state || busy) return;
    busy = true;updateSave();message.textContent = '';
    try {
      const result = await api.request('/api/favorites/'+action,{...body,deviceId:state.deviceId,requestId:requestId(),timestamp:Date.now()/1000,expectedRevision:state.status.controlRevision,expectedEpoch:state.status.controlEpoch});
      render(result.favorites);message.textContent = action === 'add' ? '已保存到 Mac。':'已删除收藏，当前会话不受影响。';
      if (action === 'add') name.value = '';
    } catch (error) { message.textContent = error.message; }
    finally { busy = false;updateSave(); }
  }
  name.addEventListener('input',updateSave);
  save.addEventListener('click',()=>mutate('add',{name:name.value.trim(),point:api.getDraft()}));
  window.addEventListener('loc2:draft',updateSave);
  window.addEventListener('loc2:status',()=>load());
  setInterval(()=>load(true),5000);load();
})();
