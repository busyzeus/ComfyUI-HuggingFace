import { HuggingFaceDownloaderAPI } from "../../api/huggingface.js";

// Nothing downloads from the search tab. Rows hand off to the Download tab so
// the user sees the file list and size warning before committing.
export async function handleSearchSubmit(ui, { append = false } = {}) {
    if (!append) {
        ui.searchState.page = 1;
        ui.searchState.query = ui.searchQueryInput.value.trim();
        ui.searchState.category = ui.searchCategorySelect.value;
        ui.searchState.comfyuiOnly = ui.searchComfyuiOnlyCheckbox.checked;
        ui.searchState.sort = ui.searchSortSelect.value;
        ui.searchResultsContainer.innerHTML = '<p><i class="fas fa-spinner fa-spin"></i> Searching...</p>';
    }
    if (ui.searchLoadMoreButton) ui.searchLoadMoreButton.style.display = 'none';

    ui.searchSubmitButton.disabled = true;
    ui.searchSubmitButton.textContent = 'Searching...';
    ui.ensureFontAwesome();

    const params = {
        query: ui.searchState.query,
        category: ui.searchState.category,
        comfyui_only: ui.searchState.comfyuiOnly,
        sort: ui.searchState.sort,
        limit: ui.searchState.limit,
        page: ui.searchState.page,
        api_key: ui.settings.apiKey,
    };

    try {
        const response = await HuggingFaceDownloaderAPI.searchModels(params);
        if (!response || !response.metadata || !Array.isArray(response.items)) {
            throw new Error("Received invalid data from the search API.");
        }

        ui.renderSearchResults(response.items, { append });

        if (ui.searchLoadMoreButton) {
            ui.searchLoadMoreButton.style.display = response.metadata.has_more ? '' : 'none';
        }
    } catch (error) {
        const message = `Search failed: ${error.details || error.message || 'Unknown error'}`;
        console.error("Search Submit Error:", error);
        if (!append) {
            ui.searchResultsContainer.innerHTML = `<p style="color: var(--error-text, #ff6b6b);">${message}</p>`;
        }
        ui.showToast(message, 'error');
    } finally {
        ui.searchSubmitButton.disabled = false;
        ui.searchSubmitButton.textContent = 'Search';
    }
}

export async function handleSearchLoadMore(ui) {
    ui.searchState.page += 1;
    await handleSearchSubmit(ui, { append: true });
}
