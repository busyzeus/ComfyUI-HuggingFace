// Renders the download preview panel

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

// Model card text and filenames come from an arbitrary repo, so they are never
// injected as HTML.
function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ESCAPES[ch]);
}

export function renderDownloadPreview(ui, data) {
  if (!ui.downloadPreviewArea) return;
  ui.ensureFontAwesome();

  if (!data || data.success === false) {
    const message = data?.error || 'Model details not available';
    ui.downloadPreviewArea.innerHTML =
      `<p style="color: var(--input-text, #ccc);">${escapeHtml(message)}</p>`;
    return;
  }

  const modelId = data.model_id || '';
  const revision = data.revision || 'main';
  const files = Array.isArray(data.files) ? data.files : [];
  const tags = Array.isArray(data.tags) ? data.tags : [];
  const baseModel = Array.isArray(data.base_model) ? data.base_model : [];
  const stats = data.stats || {};
  const selectedFile = data.selected_file || '';
  const hfUrl = data.hf_url || `https://huggingface.co/${modelId}`;
  const modified = (stats.modified_at || '').slice(0, 10);

  const fileUrl = (path) =>
    `https://huggingface.co/${modelId}/blob/${encodeURIComponent(revision)}/` +
    path.split('/').map(encodeURIComponent).join('/');

  const sizeOf = (file) =>
    typeof file.size === 'number' ? ui.formatBytes(file.size) : 'size unknown';

  const totalSize = files.reduce((sum, f) => sum + (f.size || 0), 0);

  const badge = (text) =>
    `<span class="base-model-badge" style="margin-right: 5px;">${escapeHtml(text)}</span>`;

  const fileOptions = files.map(f => {
    const selected = f.path === selectedFile ? ' selected' : '';
    return `<option value="${escapeHtml(f.path)}"${selected}>${escapeHtml(f.path)} • ${sizeOf(f)}</option>`;
  }).join('');

  // Whole-repo downloads are a real footgun on repos that ship several
  // variants of the same weights, so say how much that would actually cost.
  const repoWarning = (!selectedFile && files.length > 1)
    ? `<p style="font-size: 0.9em; color: #e0a030; margin-top: 8px;">
         <i class="fas fa-exclamation-triangle"></i>
         No file selected, so the whole repo downloads: ${files.length} files, ${ui.formatBytes(totalSize)}.
       </p>`
    : '';

  ui.downloadPreviewArea.innerHTML = `
    <div class="huggingface-search-item" style="background-color: var(--comfy-input-bg); padding: 10px;">
      <div class="huggingface-search-info">
        <h4>${escapeHtml(data.model_name || modelId)}
          <span style="font-weight: normal; font-size: 0.9em;">by ${escapeHtml(data.creator_username || 'Unknown')}</span>
        </h4>
        <p style="font-size: 0.9em; color: #ccc;">
          ${badge(data.license || 'Unknown')}
          ${baseModel.map(badge).join('')}
          ${modified ? `Updated ${escapeHtml(modified)}` : ''}
        </p>
        <div class="huggingface-search-stats" title="Downloads / Likes">
          <span title="Downloads"><i class="fas fa-download"></i> ${(stats.downloads || 0).toLocaleString()}</span>
          <span title="Likes"><i class="fas fa-heart"></i> ${(stats.likes || 0).toLocaleString()}</span>
          <span title="Files"><i class="fas fa-file"></i> ${files.length} files • ${ui.formatBytes(totalSize)}</span>
        </div>
        ${files.length > 0 ? `
          <div class="huggingface-form-group" style="margin-top: 10px;">
            <label for="huggingface-file-picker">File to download</label>
            <select id="huggingface-file-picker" class="huggingface-select">
              <option value="">Entire repo (${files.length} files, ${ui.formatBytes(totalSize)})</option>
              ${fileOptions}
            </select>
            <p style="font-size: 0.9em; color: #aaa; margin-top: 6px;">Picking a file rewrites the URL above and preselects a save location.</p>
          </div>
        ` : ''}
        ${repoWarning}
        <a href="${escapeHtml(hfUrl)}" target="_blank" rel="noopener noreferrer" class="huggingface-button small" title="Open on HuggingFace website" style="margin-top: 5px; display: inline-block;">
          View on HuggingFace <i class="fas fa-external-link-alt"></i>
        </a>
      </div>
    </div>
    ${tags.length ? `
      <div style="margin-top: 10px; font-size: 0.85em; color: #aaa;">
        ${tags.map(t => escapeHtml(t)).join(' · ')}
      </div>` : ''}
    ${data.description ? `
      <div style="margin-top: 15px;">
        <h5 style="margin-bottom: 5px;">Model Card:</h5>
        <div class="model-description-content" style="max-height: 200px; overflow-y: auto; background-color: var(--comfy-input-bg); padding: 10px; border-radius: 4px; font-size: 0.9em; border: 1px solid var(--border-color, #555); white-space: pre-wrap;">${escapeHtml(data.description)}</div>
      </div>` : ''}
  `;

  const picker = ui.downloadPreviewArea.querySelector('#huggingface-file-picker');
  if (!picker) return;
  picker.addEventListener('change', async () => {
    const path = picker.value;
    if (ui.modelUrlInput) {
      ui.modelUrlInput.value = path ? fileUrl(path) : hfUrl;
      // Re-render off the new URL so the panel keeps matching it - otherwise the
      // whole-repo warning survives after a file has been picked.
      ui.modelUrlInput.dispatchEvent(new Event('input', { bubbles: true }));
    }
    // Comfy-Org repos name their folders after the ComfyUI models/ subfolder
    const folder = path.includes('/') ? path.split('/')[0] : null;
    if (folder) await ui.autoSelectModelTypeFromHuggingFace(folder);
  });
}
