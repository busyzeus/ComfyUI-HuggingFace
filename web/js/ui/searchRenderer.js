// Rendering of search results list
// Usage: renderSearchResults(uiInstance, itemsArray, { append })

// Repo names, authors and tags come from arbitrary repos, so never inject them.
import { escapeHtml } from "../utils/escapeHtml.js";

function formatCount(value) {
  return Number(value || 0).toLocaleString();
}

function formatDate(iso) {
  if (!iso) return '';
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? ''
    : date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

export function renderSearchResults(ui, items, { append = false } = {}) {
  ui.ensureFontAwesome();

  if (!append && (!items || items.length === 0)) {
    const searched = ui.searchQueryInput?.value.trim()
      || ui.searchCategorySelect?.value !== 'any'
      || ui.searchComfyuiOnlyCheckbox?.checked;
    ui.searchResultsContainer.innerHTML = searched
      ? '<p>No models found matching your criteria.</p>'
      : '<p>Enter a query or choose a filter, then click Search.</p>';
    return;
  }

  const fragment = document.createDocumentFragment();

  (items || []).forEach(item => {
    if (!item.id) return;

    const updated = formatDate(item.updated);
    const tags = Array.isArray(item.tags) ? item.tags.slice(0, 5) : [];

    const listItem = document.createElement('div');
    listItem.className = 'huggingface-search-item';
    listItem.dataset.modelId = item.id;
    listItem.innerHTML = `
      <div class="huggingface-search-info">
        <h4>${item.gated ? '<span class="base-model-badge" title="Access must be requested on HuggingFace">gated</span> ' : ''}${escapeHtml(item.name)}
          <span style="font-weight: normal; font-size: 0.9em;">by ${escapeHtml(item.author)}</span>
        </h4>
        <div class="huggingface-search-stats">
          <span title="Downloads"><i class="fas fa-download"></i> ${formatCount(item.downloads)}</span>
          <span title="Likes"><i class="fas fa-heart"></i> ${formatCount(item.likes)}</span>
          ${updated ? `<span title="Last updated"><i class="fas fa-calendar-alt"></i> ${escapeHtml(updated)}</span>` : ''}
        </div>
        ${tags.length ? `
        <div class="huggingface-search-tags" title="${escapeHtml(tags.join(', '))}">
          ${tags.map(tag => `<span class="huggingface-search-tag">${escapeHtml(tag)}</span>`).join('')}
        </div>` : ''}
      </div>
      <div class="huggingface-search-actions">
        <button type="button" class="huggingface-button primary small huggingface-search-open-button"
                data-model-id="${escapeHtml(item.id)}"
                title="Open in the Download tab to see its files">
          Open in Download tab <i class="fas fa-arrow-right"></i>
        </button>
        <a href="https://huggingface.co/${escapeHtml(item.id)}"
           target="_blank" rel="noopener noreferrer" class="huggingface-button small"
           title="Open on the HuggingFace website">
          View <i class="fas fa-external-link-alt"></i>
        </a>
      </div>
    `;
    fragment.appendChild(listItem);
  });

  if (!append) ui.searchResultsContainer.innerHTML = '';
  ui.searchResultsContainer.appendChild(fragment);
}
