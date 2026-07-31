import { HuggingFaceDownloaderAPI } from "../../api/huggingface.js";
export function setupEventListeners(ui) {
    // Modal close
    ui.closeButton.addEventListener('click', () => ui.closeModal());
    ui.modal.addEventListener('click', (event) => {
        if (event.target === ui.modal) ui.closeModal();
    });

    // Tab switching
    ui.tabContainer.addEventListener('click', (event) => {
        if (event.target.matches('.huggingface-downloader-tab')) {
            ui.switchTab(event.target.dataset.tab);
        }
    });

    // --- FORMS ---
    ui.downloadForm.addEventListener('submit', (event) => {
        event.preventDefault();
        ui.handleDownloadSubmit();
    });

    // Change of model type should refresh subdir list
    ui.downloadModelTypeSelect.addEventListener('change', async () => {
        await ui.loadAndPopulateSubdirs(ui.downloadModelTypeSelect.value);
    });

    // Create new model type folder (first-level under models/)
    ui.createModelTypeButton.addEventListener('click', async () => {
        const name = prompt('Enter new model type folder name (will be created under models/)');
        if (!name) return;
        try {
            const res = await HuggingFaceDownloaderAPI.createModelType(name);
            if (res && res.success) {
                await ui.populateModelTypes();
                ui.downloadModelTypeSelect.value = res.name;
                await ui.loadAndPopulateSubdirs(res.name);
                ui.showToast(`Created model type folder: ${res.name}`, 'success');
            } else {
                ui.showToast(res?.error || 'Failed to create model type folder', 'error');
            }
        } catch (e) {
            ui.showToast(e.details || e.message || 'Error creating model type folder', 'error');
        }
    });

    // Create new subfolder under current model type
    ui.createSubdirButton.addEventListener('click', async () => {
        const type = ui.downloadModelTypeSelect.value;
        const name = prompt('Enter new subfolder name (you can include nested paths like A/B):');
        if (!name) return;
        try {
            const res = await HuggingFaceDownloaderAPI.createModelDir(type, name);
            if (res && res.success) {
                await ui.loadAndPopulateSubdirs(type);
                if (ui.subdirSelect) ui.subdirSelect.value = res.created || '';
                ui.showToast(`Created folder: ${res.created}`, 'success');
            } else {
                ui.showToast(res?.error || 'Failed to create folder', 'error');
            }
        } catch (e) {
            ui.showToast(e.details || e.message || 'Error creating folder', 'error');
        }
    });

    ui.searchForm.addEventListener('submit', (event) => {
        event.preventDefault();
        const hasQuery = ui.searchQueryInput.value.trim();
        const hasFilter = ui.searchCategorySelect.value !== 'any' || ui.searchComfyuiOnlyCheckbox.checked;
        if (!hasQuery && !hasFilter) {
            ui.showToast("Enter a search query or choose a filter.", "error");
            ui.searchResultsContainer.innerHTML = '<p>Enter a query or choose a filter, then click Search.</p>';
            if (ui.searchLoadMoreButton) ui.searchLoadMoreButton.style.display = 'none';
            return;
        }
        ui.handleSearchSubmit();
    });

    if (ui.searchLoadMoreButton) {
        ui.searchLoadMoreButton.addEventListener('click', () => ui.handleSearchLoadMore());
    }

    ui.settingsForm.addEventListener('submit', (event) => {
        event.preventDefault();
        ui.handleSettingsSave();
    });
    if (ui.settingsSetGlobalRootButton) {
        ui.settingsSetGlobalRootButton.addEventListener('click', () => {
            ui.handleSetGlobalRoot();
        });
    }
    if (ui.settingsClearGlobalRootButton) {
        ui.settingsClearGlobalRootButton.addEventListener('click', () => {
            ui.handleClearGlobalRoot();
        });
    }

    // Download form inputs
    ui.modelUrlInput.addEventListener('input', () => ui.debounceFetchDownloadPreview());
    ui.modelUrlInput.addEventListener('paste', () => ui.debounceFetchDownloadPreview(0));

    // --- DYNAMIC CONTENT LISTENERS (Event Delegation) ---

    // Status tab actions (Cancel/Retry/Open/Clear) and click-to-toggle blur on thumbs
    ui.statusContent.addEventListener('click', (event) => {
        const thumbContainer = event.target.closest('.huggingface-thumbnail-container');
        if (thumbContainer) {
            const nsfwLevel = Number(thumbContainer.dataset.nsfwLevel ?? thumbContainer.getAttribute('data-nsfw-level'));
            const threshold = Number(ui.settings?.nsfwBlurMinLevel ?? 4);
            const enabled = ui.settings?.hideMatureInSearch === true;
            if (enabled && Number.isFinite(nsfwLevel) && nsfwLevel >= threshold) {
                if (thumbContainer.classList.contains('blurred')) {
                    thumbContainer.classList.remove('blurred');
                    const overlay = thumbContainer.querySelector('.huggingface-nsfw-overlay');
                    if (overlay) overlay.remove();
                } else {
                    thumbContainer.classList.add('blurred');
                    if (!thumbContainer.querySelector('.huggingface-nsfw-overlay')) {
                        const ov = document.createElement('div');
                        ov.className = 'huggingface-nsfw-overlay';
                        ov.title = 'R-rated: click to reveal';
                        ov.textContent = 'R';
                        thumbContainer.appendChild(ov);
                    }
                }
                return; // consume
            }
        }

        const button = event.target.closest('button');
        if (!button) return;

        const downloadId = button.dataset.id;
        if (downloadId) {
            if (button.classList.contains('huggingface-cancel-button')) ui.handleCancelDownload(downloadId);
            else if (button.classList.contains('huggingface-retry-button')) ui.handleRetryDownload(downloadId, button);
            else if (button.classList.contains('huggingface-openpath-button')) ui.handleOpenPath(downloadId, button);
        } else if (button.id === 'huggingface-clear-history-button') {
            ui.confirmClearModal.style.display = 'flex';
        }
    });

    // Download preview click-to-toggle blur
    ui.downloadPreviewArea.addEventListener('click', (event) => {
        const thumbContainer = event.target.closest('.huggingface-thumbnail-container');
        if (thumbContainer) {
            const nsfwLevel = Number(thumbContainer.dataset.nsfwLevel ?? thumbContainer.getAttribute('data-nsfw-level'));
            const threshold = Number(ui.settings?.nsfwBlurMinLevel ?? 4);
            const enabled = ui.settings?.hideMatureInSearch === true;
            if (enabled && Number.isFinite(nsfwLevel) && nsfwLevel >= threshold) {
                if (thumbContainer.classList.contains('blurred')) {
                    thumbContainer.classList.remove('blurred');
                    const overlay = thumbContainer.querySelector('.huggingface-nsfw-overlay');
                    if (overlay) overlay.remove();
                } else {
                    thumbContainer.classList.add('blurred');
                    if (!thumbContainer.querySelector('.huggingface-nsfw-overlay')) {
                        const ov = document.createElement('div');
                        ov.className = 'huggingface-nsfw-overlay';
                        ov.title = 'R-rated: click to reveal';
                        ov.textContent = 'R';
                        thumbContainer.appendChild(ov);
                    }
                }
            }
        }
    });

    // Search results: hand a repo to the Download tab, which shows its files
    // and sizes before anything downloads.
    ui.searchResultsContainer.addEventListener('click', (event) => {
        const openButton = event.target.closest('.huggingface-search-open-button');
        if (!openButton) return;
        event.preventDefault();
        const modelId = openButton.dataset.modelId;
        if (!modelId) return;

        ui.modelUrlInput.value = modelId;
        ui.customFilenameInput.value = '';
        ui.forceRedownloadCheckbox.checked = false;
        ui.switchTab('download');
        ui.fetchAndDisplayDownloadPreview();
    });

    // Confirmation Modal
    ui.confirmClearYesButton.addEventListener('click', () => ui.handleClearHistory());
    ui.confirmClearNoButton.addEventListener('click', () => {
        ui.confirmClearModal.style.display = 'none';
    });
    ui.confirmClearModal.addEventListener('click', (event) => {
        if (event.target === ui.confirmClearModal) {
            ui.confirmClearModal.style.display = 'none';
        }
    });
}
