import { HuggingFaceDownloaderAPI } from "../../api/huggingface.js";

export function debounceFetchDownloadPreview(ui, delay = 500) {
    clearTimeout(ui.modelPreviewDebounceTimeout);
    ui.modelPreviewDebounceTimeout = setTimeout(() => {
        fetchAndDisplayDownloadPreview(ui);
    }, delay);
}

export async function fetchAndDisplayDownloadPreview(ui) {
    const modelUrlOrId = ui.modelUrlInput.value.trim();

    if (!modelUrlOrId) {
        ui.downloadPreviewArea.innerHTML = '';
        return;
    }

    ui.downloadPreviewArea.innerHTML = '<p><i class="fas fa-spinner fa-spin"></i> Loading model details...</p>';
    ui.ensureFontAwesome();

    const params = {
        model_url_or_id: modelUrlOrId,
        api_key: ui.settings.apiKey
    };

    try {
        const result = await HuggingFaceDownloaderAPI.getModelDetails(params);
        // renderDownloadPreview also renders the "no details" case, and escapes
        // anything the repo supplied on the way in.
        ui.renderDownloadPreview(result);
        // Preselect the save location from the repo's folder layout
        if (result?.success && result.model_type) {
            await ui.autoSelectModelTypeFromHuggingFace(result.model_type);
        }
    } catch (error) {
        // Don't show scary error messages - just neutral info
        const message = 'Model details not available';
        console.info("Download Preview - details not available:", error);
        ui.downloadPreviewArea.innerHTML = `<p style="color: var(--input-text, #ccc);">${message}</p>`;
    }
}

export async function handleDownloadSubmit(ui) {
    ui.downloadSubmitButton.disabled = true;
    ui.downloadSubmitButton.textContent = 'Starting...';

    const modelUrlOrId = ui.modelUrlInput.value.trim();
    if (!modelUrlOrId) {
        ui.showToast("Model URL or ID cannot be empty.", "error");
        ui.downloadSubmitButton.disabled = false;
        ui.downloadSubmitButton.textContent = 'Start Download';
        return;
    }

    // Subfolder comes from dropdown; filename is base name only
    const selectedSubdir = ui.subdirSelect ? ui.subdirSelect.value.trim() : '';
    const userFilename = ui.customFilenameInput.value.trim();

    const params = {
        model_url_or_id: modelUrlOrId,
        model_type: ui.downloadModelTypeSelect.value,
        custom_filename: userFilename,
        subdir: selectedSubdir,
        num_connections: parseInt(ui.downloadConnectionsInput.value, 10),
        force_redownload: ui.forceRedownloadCheckbox.checked,
        api_key: ui.settings.apiKey
    };

    try {
        const result = await HuggingFaceDownloaderAPI.downloadModel(params);

        if (result.status === 'queued') {
            ui.showToast(`Download queued: ${result.details?.filename || 'Model'}`, 'success');
            if (ui.settings.autoOpenStatusTab) {
                ui.switchTab('status');
            } else {
                ui.updateStatus();
            }
        } else if (result.status === 'exists' || result.status === 'exists_size_mismatch') {
            ui.showToast(`${result.message}`, 'info', 4000);
        } else {
            console.warn("Unexpected success response from /huggingface/download:", result);
            ui.showToast(`Unexpected status: ${result.status} - ${result.message || ''}`, 'info');
        }
    } catch (error) {
        const message = `Download failed: ${error.details || error.message || 'Unknown error'}`;
        console.error("Download Submit Error:", error);
        ui.showToast(message, 'error', 6000);
    } finally {
        ui.downloadSubmitButton.disabled = false;
        ui.downloadSubmitButton.textContent = 'Start Download';
    }
}
