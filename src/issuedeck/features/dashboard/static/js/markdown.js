/*
 * Markdown rendering for the dashboard (IS-0004).
 *
 * window.renderMarkdown(source) returns HTML that is safe to put in innerHTML:
 *  - raw HTML in the Markdown is shown as text, never executed;
 *  - links and images are only active for http, https, mailto or relative
 *    addresses (so javascript: and data: addresses are dropped);
 *  - links to other sites open in a new tab without access to this page.
 *
 * It uses a separate marked instance, so the global marked is left untouched.
 * The styling lives in the .md-content rules of the dashboard stylesheet.
 */
(function (root) {
  'use strict';

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // Returns the address if it is safe to use, otherwise null.
  function safeUrl(href) {
    if (href == null) return null;
    var url = String(href).trim();
    if (!url) return null;
    if (/^(https?:|mailto:)/i.test(url)) return url;
    // Any other scheme (javascript:, data:, vbscript:, file: ...) is refused.
    // Control characters and whitespace are removed first, as browsers ignore them.
    if (/^[a-z][a-z0-9+.-]*:/i.test(url.replace(/[\u0000- ]/g, ''))) return null;
    return url;
  }

  function isExternal(url) {
    return /^(https?:)?\/\//i.test(url);
  }

  var renderer = {
    // Raw HTML (block or inline) is displayed literally.
    html: function (token) {
      return escapeHtml(typeof token === 'string' ? token : token.text);
    },
    link: function (token) {
      var inner = this.parser.parseInline(token.tokens);
      var url = safeUrl(token.href);
      if (url === null) return inner;
      var attrs = ' href="' + escapeHtml(url) + '"';
      if (token.title) attrs += ' title="' + escapeHtml(token.title) + '"';
      if (isExternal(url)) attrs += ' target="_blank" rel="noopener noreferrer"';
      return '<a' + attrs + '>' + inner + '</a>';
    },
    image: function (token) {
      var url = safeUrl(token.href);
      if (url === null) return escapeHtml(token.text || '');
      var attrs = ' src="' + escapeHtml(url) + '" alt="' + escapeHtml(token.text || '') + '"';
      if (token.title) attrs += ' title="' + escapeHtml(token.title) + '"';
      return '<img' + attrs + ' loading="lazy">';
    },
  };

  var instance = null;

  function getInstance() {
    if (!instance) {
      if (!root.marked || !root.marked.Marked) {
        throw new Error('marked is not loaded');
      }
      instance = new root.marked.Marked({ gfm: true, breaks: false, async: false, renderer: renderer });
    }
    return instance;
  }

  root.renderMarkdown = function (source) {
    if (source === null || source === undefined || source === '') return '';
    return getInstance().parse(String(source));
  };
})(typeof window !== 'undefined' ? window : globalThis);
