/*
 * The GitHub export and import page (FEA-0008).
 *
 * A form marked data-github-job does not reload the page. This script sends it in the
 * background (the server answers with a job id at once), then asks for the job's progress every
 * few hundred milliseconds: it shows the steps done so far and the elapsed time, and when the
 * job is finished it puts the server-rendered result into the element named by
 * data-github-target. The buttons are disabled while a job runs. Without this script the
 * forms are ordinary posts and work as before.
 *
 *   data-github-section the page section that holds the status panel (on the section)
 *   data-github-job      the form runs as a job
 *   data-github-url      post here instead of the form's action (used by a GET form)
 *   data-github-target   selector of the element that receives the result
 *   data-github-clears   selector of an element to empty when the job is done
 *   data-github-clear    on a link or button: empty the element it names
 */
(function () {
  'use strict';

  var POLL_MS = 400;
  var MAX_POLL_FAILURES = 5;
  var JOB_URL = '/dashboard/github/jobs/';
  var HEADERS = { 'X-Requested-With': 'github-job' };
  var lastSubmitter = null;

  function setHidden(element, hidden) {
    if (hidden) element.setAttribute('hidden', '');
    else element.removeAttribute('hidden');
  }

  function seconds(value) {
    return (Math.round(value * 10) / 10).toFixed(1);
  }

  // The page's own section (it holds the status panel). A result can contain sections too,
  // for instance the snapshot card, so "the nearest section" would be the wrong one.
  function sectionOf(form) {
    return form.closest('[data-github-section]') || form.closest('section') || document;
  }

  function panelFor(form) {
    return sectionOf(form).querySelector('[data-github-status]');
  }

  function partsOf(panel) {
    return {
      headline: panel.querySelector('[data-github-headline]'),
      elapsed: panel.querySelector('[data-github-elapsed]'),
      steps: panel.querySelector('[data-github-steps]'),
      error: panel.querySelector('[data-github-error]'),
      spinner: panel.querySelector('[data-github-spinner]'),
    };
  }

  function label(panel, name, value) {
    return (panel.getAttribute('data-text-' + name) || '').replace('{seconds}', value);
  }

  // While a job runs, every button of the section's job forms is disabled, so an action
  // cannot be started twice and two actions cannot overlap.
  function setBusy(form, busy) {
    form.setAttribute('aria-busy', busy ? 'true' : 'false');
    var buttons = sectionOf(form).querySelectorAll(
      'form[data-github-job] button, form[data-github-job] input[type="submit"]');
    Array.prototype.forEach.call(buttons, function (button) {
      if (busy) {
        button.setAttribute('data-github-was-disabled', button.disabled ? '1' : '0');
        button.disabled = true;
      } else {
        button.disabled = button.getAttribute('data-github-was-disabled') === '1';
        button.removeAttribute('data-github-was-disabled');
      }
    });
  }

  function showSteps(parts, steps, running) {
    parts.steps.textContent = '';
    steps.forEach(function (text, index) {
      var item = document.createElement('li');
      var current = running && index === steps.length - 1;
      item.textContent = (current ? '… ' : '✓ ') + text;
      if (current) item.setAttribute('aria-current', 'step');
      parts.steps.appendChild(item);
    });
  }

  function place(form, html) {
    var selector = form.getAttribute('data-github-target');
    var target = selector ? document.querySelector(selector) : null;
    if (target) {
      target.innerHTML = html;
      if (target.scrollIntoView) target.scrollIntoView({ block: 'nearest' });
    }
    var clears = form.getAttribute('data-github-clears');
    var cleared = clears ? document.querySelector(clears) : null;
    if (cleared) cleared.textContent = '';
  }

  function formBody(form, submitter) {
    var params = new URLSearchParams();
    new FormData(form).forEach(function (value, key) {
      if (typeof value === 'string') params.append(key, value);
    });
    if (submitter && submitter.name && form.contains(submitter)) {
      params.append(submitter.name, submitter.value);
    }
    return params.toString();
  }

  function run(form, submitter) {
    var panel = panelFor(form);
    var parts = partsOf(panel);
    var url = form.getAttribute('data-github-url') || form.getAttribute('action') ||
      window.location.pathname;
    var startedAt = Date.now();

    setHidden(panel, false);
    setHidden(parts.error, true);
    parts.error.textContent = '';
    setHidden(parts.spinner, false);
    parts.headline.textContent = label(panel, 'working', '');
    parts.steps.textContent = '';
    parts.elapsed.textContent = '0.0 s';
    setBusy(form, true);
    var timer = setInterval(function () {
      parts.elapsed.textContent = seconds((Date.now() - startedAt) / 1000) + ' s';
    }, 250);

    function finish(ok, elapsed) {
      clearInterval(timer);
      var took = seconds(elapsed != null ? elapsed : (Date.now() - startedAt) / 1000);
      setHidden(parts.spinner, true);
      parts.elapsed.textContent = took + ' s';
      parts.headline.textContent = label(panel, ok ? 'done' : 'failed', took);
      setBusy(form, false);
    }

    function fail(message, elapsed) {
      parts.error.textContent = message || label(panel, 'lost', '');
      setHidden(parts.error, false);
      finish(false, elapsed);
    }

    function poll(jobId, failures) {
      fetch(JOB_URL + encodeURIComponent(jobId), {
        credentials: 'same-origin', cache: 'no-store', headers: HEADERS,
      }).then(function (response) {
        return response.json();
      }).then(function (job) {
        showSteps(parts, job.steps || [], job.state === 'running');
        if (job.state === 'running') {
          setTimeout(function () { poll(jobId, 0); }, POLL_MS);
        } else if (job.state === 'done') {
          place(form, job.html);
          finish(true, job.elapsed);
        } else {
          fail(job.error, job.elapsed);
        }
      }, function () {
        if (failures + 1 >= MAX_POLL_FAILURES) fail(null, null);
        else setTimeout(function () { poll(jobId, failures + 1); }, POLL_MS * 2);
      });
    }

    fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: Object.assign({ 'Content-Type': 'application/x-www-form-urlencoded' }, HEADERS),
      body: formBody(form, submitter),
    }).then(function (response) {
      return response.json().then(function (body) {
        return { ok: response.ok, body: body };
      }, function () {
        return { ok: false, body: {} };
      });
    }).then(function (result) {
      if (!result.ok || !result.body.job) fail(result.body.error, null);
      else poll(result.body.job, 0);
    }, function () {
      fail(null, null);
    });
  }

  document.addEventListener('click', function (event) {
    var target = event.target;
    if (!target || !target.closest) return;
    var submit = target.closest('button[type="submit"], input[type="submit"], button:not([type])');
    if (submit) lastSubmitter = submit;
    var clear = target.closest('[data-github-clear]');
    if (clear) {
      event.preventDefault();
      var area = document.querySelector(clear.getAttribute('data-github-clear'));
      if (area) area.textContent = '';
    }
  });

  document.addEventListener('submit', function (event) {
    var form = event.target;
    if (!form || !form.matches || !form.matches('form[data-github-job]')) return;
    event.preventDefault();  // no page reload
    if (form.getAttribute('aria-busy') === 'true') return;
    run(form, event.submitter || lastSubmitter);
  });
})();
