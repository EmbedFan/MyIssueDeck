/*
 * Live updates for the dashboard views (FEA-0006).
 *
 * The page carries its settings in <script id="live-config">. This script listens to
 * the server-sent event stream (/dashboard/events); on a relevant event it fetches the
 * page again and swaps the regions marked data-live-region in place. Events only carry
 * identifiers, so nothing is trusted from them: the page itself is the source of truth.
 *
 * Rules:
 *  - events are batched, so a burst causes one refresh;
 *  - a region that is being edited (focused field, changed form, card being dragged)
 *    is never overwritten: a notice with an "Apply changes" button is shown instead,
 *    or the change is applied after the editing ends, as the settings say;
 *  - changed entries (data-live-key) are highlighted briefly;
 *  - without the stream the page refreshes periodically, and the stream reconnects.
 */
(function () {
  'use strict';

  var configElement = document.getElementById('live-config');
  if (!configElement) return;
  var config = JSON.parse(configElement.textContent);

  var BATCH_MS = 300;
  var CATEGORY = {
    'item.created': 'items', 'item.updated': 'items', 'item.shipped': 'items',
    'item.deleted': 'items', 'item.restored': 'items', 'relationship.changed': 'items',
    'project.changed': 'items', 'resync': 'items',
    'session.started': 'sessions', 'session.updated': 'sessions', 'session.finished': 'sessions',
    'activity.added': 'activity',
  };
  var WIDGET_REGIONS = ['agent-sessions', 'agent-sessions-count'];

  var source = null;
  var connected = false;
  var everConnected = false;
  var stopped = false;
  var batchTimer = null;
  var pollTimer = null;
  var wantAll = false;      // some pending event concerns this page
  var needsRefresh = false; // events arrived while the tab was hidden
  var blocked = {};         // region name -> new HTML that could not be applied yet
  var notice = null;

  // ---- connection indicator ----------------------------------------------------

  function setState(state) {
    var indicator = document.getElementById('live-indicator');
    if (!indicator) return;
    indicator.setAttribute('data-state', state);
    ['connecting', 'connected', 'offline'].forEach(function (name) {
      var part = indicator.querySelector('[data-live-state="' + name + '"]');
      if (part) part.classList.toggle('hidden', name !== state);
    });
    indicator.setAttribute('title', config.strings[state] || '');
  }

  // ---- editing guard -------------------------------------------------------------

  // A region becomes "dirty" as soon as the user changes a field in it.
  function markDirty(event) {
    var region = event.target.closest && event.target.closest('[data-live-region]');
    if (region && event.target.matches('input, textarea, select, [contenteditable="true"]')) {
      region.setAttribute('data-live-dirty', '1');
    }
  }
  document.addEventListener('input', markDirty);
  document.addEventListener('change', markDirty);

  function isBusy(region, name) {
    var active = document.activeElement;
    if (active && region.contains(active) &&
        active.matches('input, textarea, select, [contenteditable="true"]')) return true;
    if (region.hasAttribute('data-live-dirty')) return true;
    if (name === 'board' &&
        document.querySelector('.sortable-chosen, .sortable-ghost, .sortable-drag')) return true;
    return false;
  }

  // ---- applying a fetched page -----------------------------------------------------

  // The highlight class is set by this script, so it never counts as a change.
  function plain(html) {
    return html.replace(/ live-changed/g, '');
  }

  function keyedHtml(region) {
    var map = {};
    region.querySelectorAll('[data-live-key]').forEach(function (element) {
      map[element.getAttribute('data-live-key')] = plain(element.outerHTML);
    });
    return map;
  }

  function highlight(region, before) {
    var seconds = config.highlight_seconds;
    if (!seconds) return;
    region.querySelectorAll('[data-live-key]').forEach(function (element) {
      var key = element.getAttribute('data-live-key');
      if (before[key] !== plain(element.outerHTML)) {
        element.classList.add('live-changed');
        setTimeout(function () { element.classList.remove('live-changed'); }, seconds * 1000);
      }
    });
  }

  function swap(region, replacement) {
    var before = keyedHtml(region);
    region.innerHTML = replacement.innerHTML;
    region.removeAttribute('data-live-dirty');
    highlight(region, before);
  }

  function apply(doc, onlyWidget) {
    var applied = [];
    document.querySelectorAll('[data-live-region]').forEach(function (region) {
      var name = region.getAttribute('data-live-region');
      if (onlyWidget && WIDGET_REGIONS.indexOf(name) === -1) return;
      var replacement = doc.querySelector('[data-live-region="' + name + '"]');
      if (!replacement) return;
      if (plain(region.innerHTML) === replacement.innerHTML) { delete blocked[name]; return; }
      if (isBusy(region, name)) {
        blocked[name] = replacement.innerHTML;
        return;
      }
      swap(region, replacement);
      delete blocked[name];
      applied.push(name);
    });
    if (applied.length) {
      document.dispatchEvent(new CustomEvent('live:applied', { detail: { regions: applied } }));
    }
    showOrHideNotice();
  }

  // ---- notice for blocked regions --------------------------------------------------

  function showOrHideNotice() {
    var names = Object.keys(blocked);
    if (!names.length || config.while_editing !== 'notice') {
      if (notice) { notice.remove(); notice = null; }
      return;
    }
    if (notice) return;
    notice = document.createElement('div');
    notice.className = 'live-notice';
    notice.setAttribute('role', 'status');
    var text = document.createElement('span');
    text.textContent = config.strings.notice;
    var button = document.createElement('button');
    button.type = 'button';
    button.textContent = config.strings.apply;
    button.addEventListener('click', applyBlocked);
    notice.appendChild(text);
    notice.appendChild(button);
    document.body.appendChild(notice);
  }

  // The user chose to take the changes: the edited regions are replaced.
  function applyBlocked() {
    var applied = [];
    Object.keys(blocked).forEach(function (name) {
      var region = document.querySelector('[data-live-region="' + name + '"]');
      if (!region) return;
      var holder = document.createElement('div');
      holder.innerHTML = blocked[name];
      swap(region, holder);
      applied.push(name);
    });
    blocked = {};
    if (applied.length) {
      document.dispatchEvent(new CustomEvent('live:applied', { detail: { regions: applied } }));
    }
    showOrHideNotice();
  }

  // "Apply after saving": retry the blocked regions once the editing has ended.
  document.addEventListener('focusout', function () {
    if (config.while_editing !== 'after_save' || !Object.keys(blocked).length) return;
    setTimeout(function () { refresh(false); }, 250);
  });

  // A drag ended (the page announces it with "live:idle" once the move is saved or refused):
  // apply what was held back while the card was being dragged. A drop ends the interaction,
  // so this applies in both editing modes.
  document.addEventListener('live:idle', function () {
    if (!Object.keys(blocked).length) return;
    setTimeout(function () { refresh(false); }, 250);
  });

  // ---- refreshing --------------------------------------------------------------------

  function refresh(onlyWidget) {
    if (stopped) return Promise.resolve();
    if (document.hidden) { needsRefresh = true; return Promise.resolve(); }
    return fetch(window.location.href, {
      credentials: 'same-origin',
      cache: 'no-store',
      headers: { 'Accept': 'text/html', 'X-Live-Update': '1' },
    }).then(function (response) {
      if (response.redirected && /\/login/.test(response.url)) {
        stop();  // the session has ended; the next navigation asks for the login
        return null;
      }
      if (!response.ok) return null;
      return response.text();
    }).then(function (html) {
      if (!html) return;
      var doc = new DOMParser().parseFromString(html, 'text/html');
      apply(doc, !!onlyWidget);
    }).catch(function () { /* offline or restarting: the next event or poll tries again */ });
  }

  function schedule() {
    if (batchTimer) return;
    batchTimer = setTimeout(function () {
      var all = wantAll;
      batchTimer = null;
      wantAll = false;
      refresh(!all);
    }, BATCH_MS);
  }

  // ---- events --------------------------------------------------------------------------

  function handle(event) {
    var category = CATEGORY[event.type];
    if (!category || !config.events[category]) return;
    var sameProject = event.project_key === '*' || event.project_key === config.project_key;
    if (!sameProject) {
      // Another project: only the widget can care, and only when it shows all projects.
      // wantAll stays false, so the refresh then touches the widget regions only.
      if (config.all_projects && category === 'sessions') schedule();
      return;
    }
    if (config.view === 'item' && config.local_id && event.local_ids && event.local_ids.length &&
        event.local_ids.indexOf(config.local_id) === -1) {
      return;  // another item of the same project
    }
    wantAll = true;
    schedule();
  }

  function connect() {
    if (typeof EventSource === 'undefined') { setState('offline'); startPolling(); return; }
    setState('connecting');
    source = new EventSource('/dashboard/events');
    source.onopen = function () {
      connected = true;
      setState('connected');
      stopPolling();
      if (everConnected) { wantAll = true; schedule(); }  // events may have been missed
      everConnected = true;
    };
    source.onmessage = function (message) {
      try { handle(JSON.parse(message.data)); } catch (error) { /* ignore a bad event */ }
    };
    source.onerror = function () {
      connected = false;
      setState('offline');
      startPolling();  // the browser reconnects by itself; meanwhile refresh periodically
    };
  }

  function startPolling() {
    if (pollTimer || stopped) return;
    pollTimer = setInterval(function () { refresh(false); }, config.fallback_seconds * 1000);
  }

  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  function stop() {
    stopped = true;
    stopPolling();
    if (source) source.close();
    setState('offline');
  }

  document.addEventListener('visibilitychange', function () {
    if (!document.hidden && needsRefresh) { needsRefresh = false; refresh(false); }
  });
  window.addEventListener('beforeunload', function () { if (source) source.close(); });

  // A small surface for tests and for other scripts.
  window.dashboardLive = { handle: handle, refresh: refresh, config: config, applyBlocked: applyBlocked };

  connect();
})();
