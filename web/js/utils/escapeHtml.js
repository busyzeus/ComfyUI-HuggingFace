// Escaping for values that reach the DOM as HTML.
//
// Everything this extension renders comes from somewhere untrusted: repo
// names, authors and tags are whatever an arbitrary HuggingFace repo declares,
// and download error messages are raw API text. Three renderers need this, so
// it lives in one place - a security primitive with copies is one that gets
// hardened in one copy and forgotten in the others.
//
// Covers `"` as well as the angle brackets, so it is safe inside a quoted
// attribute, not just in text.

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ESCAPES[ch]);
}
