// File: web/js/utils/dom.js

/**
 * Dynamically adds a CSS link to the document's head.
 *
 * Prefer passing an absolute URL the caller built from its own
 * `import.meta.url`. A bare relative path still works, but it resolves against
 * THIS file rather than the caller's, which reads as a bug at the call site.
 * @param {string} href - Absolute URL of the CSS file, or a path relative to this module.
 * @param {string} [id="huggingface-downloader-styles"] - The ID for the link element.
 */
export function addCssLink(href, id = "huggingface-downloader-styles") {
  if (document.getElementById(id)) return; // Prevent duplicates

  try {
    // An already-absolute URL passes through this unchanged
    const absoluteUrl = new URL(href, import.meta.url);

    const link = document.createElement("link");
    link.id = id;
    link.rel = "stylesheet";
    link.href = absoluteUrl.href;

    link.onload = () => {
      console.log("[HuggingFace] CSS loaded successfully:", link.href);
    };
    link.onerror = () => {
      console.error("[HuggingFace] Critical error: Failed to load CSS from:", link.href);
    };

    document.head.appendChild(link);
  } catch (e) {
    console.error("[HuggingFace] Error creating CSS link. import.meta.url may be unsupported in this context.", e);
  }
}
