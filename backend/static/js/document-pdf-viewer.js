const PDFJS_VERSION = "5.3.31";
const PDFJS_MODULE_URL = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${PDFJS_VERSION}/pdf.min.mjs`;
const PDFJS_WORKER_URL = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${PDFJS_VERSION}/pdf.worker.min.mjs`;

const ZOOM_MIN = 0.5;
const ZOOM_MAX = 3.0;
const ZOOM_STEP = 0.2;
const THUMBNAIL_WIDTH = 132;

function clamp(value, minimum, maximum) {
    return Math.min(
        maximum,
        Math.max(minimum, value)
    );
}

function parsePage(value) {
    const match = String(value || "").match(/\d+/);
    const parsed = match ? Number.parseInt(match[0], 10) : 1;
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

function joinUrl(url, query) {
    return `${url}${url.includes("?") ? "&" : "?"}${query}`;
}

function escapeHtml(value) {
    return String(value || "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function normalizeWord(value) {
    return String(value || "")
        .normalize("NFKC")
        .toLocaleLowerCase();
}

function tokenizeWords(value) {
    return (String(value || "").match(/[\p{L}\p{N}]+/gu) || [])
        .map(normalizeWord)
        .filter(Boolean);
}

function pageNumbersForMatch(match) {
    const start = Number.parseInt(match?.page_start, 10);
    const end = Number.parseInt(match?.page_end, 10);

    if (!Number.isFinite(start) && !Number.isFinite(end)) {
        return [];
    }

    const first = Number.isFinite(start) ? start : end;
    const last = Number.isFinite(end) ? end : first;
    const pages = [];

    for (let page = Math.min(first, last); page <= Math.max(first, last); page += 1) {
        pages.push(page);
    }

    return pages;
}

function matchAppliesToPage(match, pageNumber) {
    return pageNumbersForMatch(match).includes(pageNumber);
}

function findBestTokenRange(pageTokens, targetWords) {
    if (!pageTokens.length || !targetWords.length) {
        return null;
    }

    const minimumWindow = Math.min(
        5,
        Math.max(2, targetWords.length)
    );

    let best = null;

    for (let windowSize = Math.min(10, targetWords.length); windowSize >= minimumWindow; windowSize -= 1) {
        for (let targetStart = 0; targetStart <= targetWords.length - windowSize; targetStart += 1) {
            const firstWord = targetWords[targetStart];

            for (let pageStart = 0; pageStart <= pageTokens.length - windowSize; pageStart += 1) {
                if (pageTokens[pageStart].word !== firstWord) {
                    continue;
                }

                let matchesWindow = true;

                for (let offset = 1; offset < windowSize; offset += 1) {
                    if (pageTokens[pageStart + offset].word !== targetWords[targetStart + offset]) {
                        matchesWindow = false;
                        break;
                    }
                }

                if (!matchesWindow) {
                    continue;
                }

                let left = 0;
                while (
                    targetStart - left - 1 >= 0
                    && pageStart - left - 1 >= 0
                    && targetWords[targetStart - left - 1]
                        === pageTokens[pageStart - left - 1].word
                ) {
                    left += 1;
                }

                let right = windowSize;
                while (
                    targetStart + right < targetWords.length
                    && pageStart + right < pageTokens.length
                    && targetWords[targetStart + right]
                        === pageTokens[pageStart + right].word
                ) {
                    right += 1;
                }

                const length = left + right;
                const candidate = {
                    start: pageStart - left,
                    end: pageStart + right - 1,
                    length,
                };

                if (!best || candidate.length > best.length) {
                    best = candidate;
                }
            }
        }

        if (best && best.length >= windowSize + 3) {
            break;
        }
    }

    return best;
}

class LifeOSPDFViewer {
    constructor(modal) {
        this.modal = modal;
        this.pdfUrl = modal.dataset.dbPdfUrl;
        this.semanticSearchUrl = modal.dataset.dbPdfSemanticSearchUrl;
        this.documentName = modal.dataset.dbDocumentName || "Document.pdf";

        this.dialog = modal.querySelector(".db-pdf-dialog");
        this.workspace = modal.querySelector("[data-db-pdf-workspace]");
        this.sidebar = modal.querySelector("[data-db-pdf-sidebar]");
        this.stage = modal.querySelector("[data-db-pdf-stage]");
        this.canvasWrap = modal.querySelector("[data-db-pdf-canvas-wrap]");
        this.pageStack = modal.querySelector("[data-db-pdf-page-stack]");
        this.canvas = modal.querySelector("[data-db-pdf-canvas]");
        this.textLayer = modal.querySelector("[data-db-pdf-text-layer]");
        this.loading = modal.querySelector("[data-db-pdf-loading]");
        this.error = modal.querySelector("[data-db-pdf-error]");
        this.errorMessage = modal.querySelector("[data-db-pdf-error-message]");
        this.status = modal.querySelector("[data-db-pdf-status]");
        this.pageInput = modal.querySelector("[data-db-pdf-page-input]");
        this.pageCount = modal.querySelector("[data-db-pdf-page-count]");
        this.zoomLabel = modal.querySelector("[data-db-pdf-zoom-label]");
        this.previousButton = modal.querySelector("[data-db-pdf-previous]");
        this.nextButton = modal.querySelector("[data-db-pdf-next]");
        this.sidebarToggle = modal.querySelector("[data-db-pdf-sidebar-toggle]");
        this.thumbnails = modal.querySelector("[data-db-pdf-thumbnails]");
        this.findForm = modal.querySelector("[data-db-pdf-find-form]");
        this.findInput = modal.querySelector("[data-db-pdf-find-input]");
        this.findStatus = modal.querySelector("[data-db-pdf-find-status]");
        this.findResults = modal.querySelector("[data-db-pdf-find-results]");
        this.matchNavigation = modal.querySelector("[data-db-pdf-match-navigation]");
        this.matchPosition = modal.querySelector("[data-db-pdf-match-position]");
        this.matchPrevious = modal.querySelector("[data-db-pdf-match-previous]");
        this.matchNext = modal.querySelector("[data-db-pdf-match-next]");
        this.progress = modal.querySelector("[data-db-pdf-progress]");
        this.progressBar = modal.querySelector("[data-db-pdf-progress-bar]");
        this.nativeFallback = modal.querySelector("[data-db-pdf-native-fallback]");
        this.fallbackFrame = modal.querySelector("[data-db-pdf-fallback-frame]");
        this.selectionToolbar = modal.querySelector("[data-db-pdf-selection-toolbar]");
        this.selectionAskButton = modal.querySelector("[data-db-pdf-selection-ask]");
        this.selectionCopyButton = modal.querySelector("[data-db-pdf-selection-copy]");

        this.askTab = document.querySelector('[data-db-tab="ask"]');
        this.askInput = document.querySelector("[data-db-question-input]");
        this.selectedContextCard = document.querySelector("[data-db-selected-context-card]");
        this.selectedContextPreview = document.querySelector("[data-db-selected-context-preview]");
        this.selectedContextLocation = document.querySelector("[data-db-selected-context-location]");
        this.selectedContextInput = document.querySelector("[data-db-selected-context-input]");
        this.selectedContextPageInput = document.querySelector("[data-db-selected-context-page-input]");
        this.selectedContextSectionInput = document.querySelector("[data-db-selected-context-section-input]");
        this.removeSelectedContextButton = document.querySelector("[data-db-remove-selected-context]");

        this.pdfjs = null;
        this.pdfDocument = null;
        this.loadingTask = null;
        this.renderTask = null;
        this.textLayerTask = null;
        this.thumbnailObserver = null;
        this.textCache = new Map();
        this.currentPage = 1;
        this.scale = 1.2;
        this.rotation = 0;
        this.fitWidth = true;
        this.sidebarVisible = true;
        this.searchToken = 0;
        this.semanticMatches = [];
        this.activeSemanticMatchIndex = -1;
        this.pendingSelection = null;
        this.attachedContext = null;
        this.fallbackActive = false;
        this.lastFocusedElement = null;
        this.resizeTimer = null;

        this.bindEvents();
    }

    bindEvents() {
        document.querySelectorAll("[data-db-open-pdf]").forEach((button) => {
            button.addEventListener("click", () => {
                this.open(parsePage(button.dataset.dbPdfPage));
            });
        });

        this.modal.querySelectorAll("[data-db-close-pdf]").forEach((button) => {
            button.addEventListener("click", () => this.close());
        });

        this.modal.querySelector("[data-db-pdf-new-tab]")?.addEventListener(
            "click",
            () => this.openNewTab()
        );

        this.modal.querySelector("[data-db-pdf-error-new-tab]")?.addEventListener(
            "click",
            () => this.openNewTab()
        );

        this.previousButton?.addEventListener("click", () => {
            this.goToPage(this.currentPage - 1);
        });

        this.nextButton?.addEventListener("click", () => {
            this.goToPage(this.currentPage + 1);
        });

        this.pageInput?.addEventListener("change", () => {
            this.goToPage(parsePage(this.pageInput.value));
        });

        this.modal.querySelector("[data-db-pdf-zoom-in]")?.addEventListener(
            "click",
            () => this.changeZoom(ZOOM_STEP)
        );

        this.modal.querySelector("[data-db-pdf-zoom-out]")?.addEventListener(
            "click",
            () => this.changeZoom(-ZOOM_STEP)
        );

        this.modal.querySelector("[data-db-pdf-fit-width]")?.addEventListener(
            "click",
            () => {
                this.fitWidth = true;
                this.renderCurrentPage();
            }
        );

        this.modal.querySelector("[data-db-pdf-rotate-left]")?.addEventListener(
            "click",
            () => this.rotate(-90)
        );

        this.modal.querySelector("[data-db-pdf-rotate-right]")?.addEventListener(
            "click",
            () => this.rotate(90)
        );

        this.modal.querySelector("[data-db-pdf-download]")?.addEventListener(
            "click",
            () => this.download()
        );

        this.modal.querySelector("[data-db-pdf-print]")?.addEventListener(
            "click",
            () => this.print()
        );

        this.sidebarToggle?.addEventListener("click", () => {
            this.setSidebarVisible(!this.sidebarVisible);
        });

        this.modal.querySelectorAll("[data-db-pdf-sidebar-view]").forEach((button) => {
            button.addEventListener("click", () => {
                this.activateSidebarView(button.dataset.dbPdfSidebarView);
            });
        });

        this.findForm?.addEventListener("submit", (event) => {
            event.preventDefault();
            this.searchSemantically(this.findInput?.value || "");
        });

        this.matchPrevious?.addEventListener("click", () => {
            this.goToSemanticMatch(this.activeSemanticMatchIndex - 1);
        });

        this.matchNext?.addEventListener("click", () => {
            this.goToSemanticMatch(this.activeSemanticMatchIndex + 1);
        });

        this.textLayer?.addEventListener("mouseup", () => {
            window.setTimeout(() => this.capturePDFSelection(), 0);
        });

        this.textLayer?.addEventListener("keyup", () => {
            window.setTimeout(() => this.capturePDFSelection(), 0);
        });

        this.selectionAskButton?.addEventListener("mousedown", (event) => {
            event.preventDefault();
        });

        this.selectionAskButton?.addEventListener("click", () => {
            this.attachPendingSelectionToAsk();
        });

        this.selectionCopyButton?.addEventListener("mousedown", (event) => {
            event.preventDefault();
        });

        this.selectionCopyButton?.addEventListener("click", () => {
            this.copyPendingSelection();
        });

        this.removeSelectedContextButton?.addEventListener("click", () => {
            this.clearAttachedContext();
        });

        document.addEventListener("mousedown", (event) => {
            if (!this.isOpen() || this.selectionToolbar?.hidden) {
                return;
            }

            if (this.selectionToolbar.contains(event.target)) {
                return;
            }

            if (this.textLayer?.contains(event.target)) {
                return;
            }

            this.hideSelectionToolbar();
        });

        window.addEventListener("resize", () => {
            if (!this.isOpen() || !this.fitWidth || this.fallbackActive) {
                return;
            }

            window.clearTimeout(this.resizeTimer);
            this.resizeTimer = window.setTimeout(() => {
                this.renderCurrentPage();
            }, 120);
        });

        document.addEventListener("keydown", (event) => this.handleKeyboard(event));
    }

    isOpen() {
        return this.modal.classList.contains("is-open");
    }

    async open(page = 1) {
        this.lastFocusedElement = document.activeElement;
        this.currentPage = page;
        this.modal.classList.add("is-open");
        this.modal.setAttribute("aria-hidden", "false");
        document.body.classList.add("db-pdf-modal-open");
        this.setStatus(`Opening page ${page}…`);

        this.dialog?.focus?.();

        if (this.pdfDocument) {
            await this.goToPage(page);
            return;
        }

        await this.loadDocument(page);
    }

    close() {
        this.hideSelectionToolbar();
        this.modal.classList.remove("is-open");
        this.modal.setAttribute("aria-hidden", "true");
        document.body.classList.remove("db-pdf-modal-open");

        if (this.lastFocusedElement instanceof HTMLElement) {
            this.lastFocusedElement.focus();
        }
    }

    async loadLibrary() {
        if (this.pdfjs) {
            return this.pdfjs;
        }

        const pdfjs = await import(PDFJS_MODULE_URL);
        pdfjs.GlobalWorkerOptions.workerSrc = PDFJS_WORKER_URL;
        this.pdfjs = pdfjs;
        return pdfjs;
    }

    async loadDocument(initialPage) {
        this.showLoading(true);
        this.showError(false);
        this.progress.hidden = false;
        this.progressBar.style.width = "4%";

        try {
            const pdfjs = await this.loadLibrary();

            this.loadingTask = pdfjs.getDocument({
                url: this.pdfUrl,
                withCredentials: true,
            });

            this.loadingTask.onProgress = ({ loaded, total }) => {
                if (!total) {
                    return;
                }
                const percent = clamp((loaded / total) * 100, 4, 100);
                this.progressBar.style.width = `${percent}%`;
            };

            this.pdfDocument = await this.loadingTask.promise;
            this.pageCount.textContent = String(this.pdfDocument.numPages);
            this.pageInput.max = String(this.pdfDocument.numPages);
            this.currentPage = clamp(initialPage, 1, this.pdfDocument.numPages);
            this.createThumbnailShells();
            this.showLoading(false);
            this.canvasWrap.hidden = false;
            await this.renderCurrentPage();
            this.progressBar.style.width = "100%";
            window.setTimeout(() => {
                this.progress.hidden = true;
                this.progressBar.style.width = "0%";
            }, 220);
        } catch (error) {
            console.error("LifeOS PDF.js viewer failed.", error);
            this.activateNativeFallback(initialPage, error);
        }
    }

    async goToPage(page) {
        if (this.fallbackActive) {
            this.currentPage = Math.max(1, page);
            this.fallbackFrame.src = `${this.pdfUrl}#page=${this.currentPage}&view=FitH`;
            return;
        }

        if (!this.pdfDocument) {
            return;
        }

        this.currentPage = clamp(page, 1, this.pdfDocument.numPages);
        await this.renderCurrentPage();
    }

    async renderCurrentPage() {
        if (!this.pdfDocument || this.fallbackActive) {
            return;
        }

        const pageNumber = clamp(
            this.currentPage,
            1,
            this.pdfDocument.numPages
        );

        this.currentPage = pageNumber;
        this.setStatus(`Rendering page ${pageNumber}…`);

        if (this.renderTask) {
            try {
                this.renderTask.cancel();
            } catch (_) {
                // A finished task does not need cancellation.
            }
        }

        const page = await this.pdfDocument.getPage(pageNumber);
        const baseViewport = page.getViewport({
            scale: 1,
            rotation: this.rotation,
        });

        let scale = this.scale;

        if (this.fitWidth) {
            const availableWidth = Math.max(
                320,
                this.stage.clientWidth - 56
            );
            scale = clamp(
                availableWidth / baseViewport.width,
                ZOOM_MIN,
                ZOOM_MAX
            );
        }

        this.scale = scale;

        const viewport = page.getViewport({
            scale,
            rotation: this.rotation,
        });

        const outputScale = window.devicePixelRatio || 1;
        const context = this.canvas.getContext("2d", { alpha: false });

        this.canvas.width = Math.floor(viewport.width * outputScale);
        this.canvas.height = Math.floor(viewport.height * outputScale);
        this.canvas.style.width = `${Math.floor(viewport.width)}px`;
        this.canvas.style.height = `${Math.floor(viewport.height)}px`;

        this.renderTask = page.render({
            canvasContext: context,
            viewport,
            transform: outputScale !== 1
                ? [outputScale, 0, 0, outputScale, 0, 0]
                : null,
        });

        try {
            await this.renderTask.promise;
        } catch (error) {
            if (error?.name !== "RenderingCancelledException") {
                throw error;
            }
            return;
        }

        await this.renderTextLayer(
            page,
            viewport
        );

        this.pageInput.value = String(pageNumber);
        this.previousButton.disabled = pageNumber <= 1;
        this.nextButton.disabled = pageNumber >= this.pdfDocument.numPages;
        this.updateZoomLabel();
        this.updateActiveThumbnail();
        this.setStatus(`Page ${pageNumber} of ${this.pdfDocument.numPages}`);
    }

    async renderTextLayer(page, viewport) {
        if (!this.textLayer || !this.pageStack) {
            return;
        }

        if (this.textLayerTask?.cancel) {
            try {
                this.textLayerTask.cancel();
            } catch (_) {
                // Finished text layers do not require cancellation.
            }
        }

        this.textLayer.replaceChildren();
        this.textLayer.style.width = `${Math.floor(viewport.width)}px`;
        this.textLayer.style.height = `${Math.floor(viewport.height)}px`;
        this.textLayer.style.setProperty(
            "--scale-factor",
            String(viewport.scale)
        );
        this.pageStack.style.width = `${Math.floor(viewport.width)}px`;
        this.pageStack.style.height = `${Math.floor(viewport.height)}px`;

        const textContent = await page.getTextContent();

        try {
            if (typeof this.pdfjs?.TextLayer !== "function") {
                throw new Error("PDF.js TextLayer is unavailable.");
            }

            const task = new this.pdfjs.TextLayer({
                textContentSource: textContent,
                container: this.textLayer,
                viewport,
            });

            this.textLayerTask = task;
            await task.render();
            this.textLayer.dataset.ready = "1";
            this.applySemanticHighlightsForCurrentPage();
            this.applyAttachedContextHighlightForCurrentPage();
        } catch (error) {
            console.warn("PDF text layer could not be rendered.", error);
            this.textLayer.dataset.ready = "0";
            this.textLayer.replaceChildren();
        }
    }

    buildPageTokenMap() {
        if (!this.textLayer || this.textLayer.dataset.ready !== "1") {
            return [];
        }

        const pageTokens = [];
        const spans = Array.from(
            this.textLayer.querySelectorAll("span")
        ).filter((span) => String(span.textContent || "").trim());

        spans.forEach((span, spanIndex) => {
            tokenizeWords(span.textContent).forEach((word) => {
                pageTokens.push({
                    word,
                    span,
                    spanIndex,
                });
            });
        });

        return pageTokens;
    }

    clearSemanticHighlights() {
        if (!this.textLayer) {
            return;
        }

        this.textLayer.querySelectorAll(".db-semantic-highlight").forEach((span) => {
            span.classList.remove(
                "db-semantic-highlight",
                "db-semantic-highlight-strong",
                "db-semantic-highlight-related"
            );
            span.removeAttribute("data-db-semantic-match-id");
        });
    }

    applySemanticHighlightsForCurrentPage() {
        this.clearSemanticHighlights();

        if (!this.semanticMatches.length) {
            return;
        }

        const matches = this.semanticMatches.filter((match) => (
            matchAppliesToPage(match, this.currentPage)
        ));

        if (!matches.length) {
            return;
        }

        const pageTokens = this.buildPageTokenMap();
        if (!pageTokens.length) {
            return;
        }

        matches.forEach((match) => {
            const targetWords = tokenizeWords(match.text);
            const range = findBestTokenRange(pageTokens, targetWords);

            if (!range) {
                return;
            }

            const spans = new Set();

            for (let index = range.start; index <= range.end; index += 1) {
                spans.add(pageTokens[index].span);
            }

            spans.forEach((span) => {
                span.classList.add("db-semantic-highlight");

                if (match.emphasis === "strong") {
                    span.classList.remove("db-semantic-highlight-related");
                    span.classList.add("db-semantic-highlight-strong");
                } else if (!span.classList.contains("db-semantic-highlight-strong")) {
                    span.classList.add("db-semantic-highlight-related");
                }

                span.dataset.dbSemanticMatchId = match.match_id;
            });
        });
    }

    updateSemanticThumbnailMarkers() {
        const pageStrength = new Map();

        this.semanticMatches.forEach((match) => {
            pageNumbersForMatch(match).forEach((pageNumber) => {
                const existing = pageStrength.get(pageNumber);
                if (existing !== "strong") {
                    pageStrength.set(
                        pageNumber,
                        match.emphasis === "strong" ? "strong" : "related"
                    );
                }
            });
        });

        this.thumbnails.querySelectorAll(".db-pdf-thumbnail").forEach((button) => {
            const pageNumber = Number.parseInt(button.dataset.page, 10);
            const emphasis = pageStrength.get(pageNumber);

            button.classList.toggle(
                "has-semantic-match",
                Boolean(emphasis)
            );
            button.classList.toggle(
                "has-strong-semantic-match",
                emphasis === "strong"
            );
        });
    }

    updateSemanticNavigation() {
        const count = this.semanticMatches.length;
        this.matchNavigation.hidden = count === 0;

        if (!count) {
            this.matchPosition.textContent = "0 of 0";
            return;
        }

        const current = clamp(
            this.activeSemanticMatchIndex + 1,
            1,
            count
        );

        this.matchPosition.textContent = `${current} of ${count}`;
        this.matchPrevious.disabled = count <= 1;
        this.matchNext.disabled = count <= 1;
    }

    async goToSemanticMatch(index) {
        const count = this.semanticMatches.length;
        if (!count) {
            return;
        }

        const normalizedIndex = (
            (index % count) + count
        ) % count;

        this.activeSemanticMatchIndex = normalizedIndex;
        const match = this.semanticMatches[normalizedIndex];
        const pages = pageNumbersForMatch(match);
        const page = pages[0] || this.currentPage;

        this.updateSemanticNavigation();
        await this.goToPage(page);
    }

    async searchSemantically(rawQuery) {
        if (!this.semanticSearchUrl || this.fallbackActive) {
            return;
        }

        const query = String(rawQuery || "").trim();
        if (!query) {
            this.semanticMatches = [];
            this.activeSemanticMatchIndex = -1;
            this.findResults.innerHTML = "";
            this.findStatus.textContent = "Search for a topic, question, or concept.";
            this.updateSemanticNavigation();
            this.updateSemanticThumbnailMarkers();
            this.applySemanticHighlightsForCurrentPage();
            return;
        }

        const token = ++this.searchToken;
        this.findResults.innerHTML = "";
        this.findStatus.textContent = "Finding related passages…";

        try {
            const url = joinUrl(
                this.semanticSearchUrl,
                `q=${encodeURIComponent(query)}`
            );

            const response = await fetch(url, {
                headers: {
                    "Accept": "application/json",
                },
                credentials: "same-origin",
            });

            const payload = await response.json().catch(() => ({}));

            if (token !== this.searchToken) {
                return;
            }

            if (!response.ok || !payload.ok) {
                throw new Error(
                    payload.message || "LifeOS could not search this PDF."
                );
            }

            this.semanticMatches = Array.isArray(payload.matches)
                ? payload.matches
                : [];
            this.activeSemanticMatchIndex = this.semanticMatches.length ? 0 : -1;

            this.updateSemanticThumbnailMarkers();
            this.updateSemanticNavigation();

            if (!this.semanticMatches.length) {
                this.findStatus.textContent = `No related passages found for “${query}”.`;
                this.findResults.innerHTML = `
                    <div class="db-pdf-find-empty">
                        Try describing the idea in another way.
                    </div>
                `;
                this.applySemanticHighlightsForCurrentPage();
                return;
            }

            const count = this.semanticMatches.length;
            let status = `${count} related ${count === 1 ? "passage" : "passages"} found.`;

            if (payload.degraded) {
                status += " Showing the best available matches.";
            }

            if (payload.limited) {
                status += " The strongest matches are shown.";
            }

            this.findStatus.textContent = status;

            this.findResults.innerHTML = this.semanticMatches.map((match, index) => `
                <button
                    type="button"
                    class="db-pdf-find-result db-pdf-semantic-result db-pdf-semantic-result-${escapeHtml(match.emphasis)}"
                    data-db-pdf-semantic-index="${index}"
                >
                    <span>
                        <strong>${escapeHtml(
                            match.page_label && match.page_label !== "Unknown"
                                ? `Page ${match.page_label}`
                                : "Related passage"
                        )}</strong>
                        ${match.section ? `<small>${escapeHtml(match.section)}</small>` : ""}
                    </span>
                    <p>${escapeHtml(match.text)}</p>
                </button>
            `).join("");

            this.findResults.querySelectorAll("[data-db-pdf-semantic-index]").forEach((button) => {
                button.addEventListener("click", () => {
                    this.goToSemanticMatch(
                        Number.parseInt(button.dataset.dbPdfSemanticIndex, 10)
                    );
                });
            });

            await this.goToSemanticMatch(0);
        } catch (error) {
            console.error("LifeOS semantic PDF search failed.", error);
            this.semanticMatches = [];
            this.activeSemanticMatchIndex = -1;
            this.updateSemanticThumbnailMarkers();
            this.updateSemanticNavigation();
            this.applySemanticHighlightsForCurrentPage();
            this.findStatus.textContent = (
                error?.message || "LifeOS could not search this PDF right now."
            );
            this.findResults.innerHTML = `
                <div class="db-pdf-find-empty">
                    Search could not be completed. Try again in a moment.
                </div>
            `;
        }
    }

    capturePDFSelection() {
        if (!this.isOpen() || this.fallbackActive || !this.textLayer) {
            return;
        }

        const selection = window.getSelection();

        if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
            this.hideSelectionToolbar();
            return;
        }

        const range = selection.getRangeAt(0);
        const commonNode = (
            range.commonAncestorContainer.nodeType === Node.ELEMENT_NODE
                ? range.commonAncestorContainer
                : range.commonAncestorContainer.parentElement
        );

        if (!commonNode || !this.textLayer.contains(commonNode)) {
            this.hideSelectionToolbar();
            return;
        }

        const text = String(selection.toString() || "")
            .replace(/\s+/g, " ")
            .trim();

        if (!text) {
            this.hideSelectionToolbar();
            return;
        }

        const spans = Array.from(
            this.textLayer.querySelectorAll("span")
        ).filter((span) => {
            try {
                return range.intersectsNode(span);
            } catch (_) {
                return false;
            }
        });

        const rect = range.getBoundingClientRect();

        this.pendingSelection = {
            text,
            page: this.currentPage,
            section: this.sectionForCurrentSelection(spans),
            spans,
        };

        if (this.selectionAskButton) {
            const tooLong = text.length > 5000;
            this.selectionAskButton.disabled = tooLong;
            this.selectionAskButton.title = tooLong
                ? "Select a smaller passage before asking about it."
                : "Ask Document about this selected passage";
        }

        this.showSelectionToolbar(rect);
    }

    sectionForCurrentSelection(spans) {
        const semanticIds = new Set();

        spans.forEach((span) => {
            if (span.dataset.dbSemanticMatchId) {
                semanticIds.add(span.dataset.dbSemanticMatchId);
            }
        });

        for (const match of this.semanticMatches) {
            if (
                semanticIds.has(match.match_id)
                && match.section
            ) {
                return String(match.section);
            }
        }

        return "";
    }

    showSelectionToolbar(rect) {
        if (!this.selectionToolbar || !rect) {
            return;
        }

        this.selectionToolbar.hidden = false;
        this.selectionToolbar.classList.add("is-visible");

        const toolbarRect = this.selectionToolbar.getBoundingClientRect();
        const margin = 12;
        const preferredLeft = (
            rect.left
            + (rect.width / 2)
            - (toolbarRect.width / 2)
        );

        const left = clamp(
            preferredLeft,
            margin,
            window.innerWidth - toolbarRect.width - margin
        );

        let top = rect.top - toolbarRect.height - 10;

        if (top < margin) {
            top = Math.min(
                window.innerHeight - toolbarRect.height - margin,
                rect.bottom + 10
            );
        }

        this.selectionToolbar.style.left = `${Math.round(left)}px`;
        this.selectionToolbar.style.top = `${Math.round(top)}px`;
    }

    hideSelectionToolbar() {
        if (!this.selectionToolbar) {
            return;
        }

        this.selectionToolbar.hidden = true;
        this.selectionToolbar.classList.remove("is-visible");
    }

    async copyPendingSelection() {
        const text = this.pendingSelection?.text;
        if (!text) {
            return;
        }

        try {
            await navigator.clipboard.writeText(text);
        } catch (_) {
            const textarea = document.createElement("textarea");
            textarea.value = text;
            textarea.setAttribute("readonly", "");
            textarea.style.position = "fixed";
            textarea.style.opacity = "0";
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand("copy");
            textarea.remove();
        }

        if (this.selectionCopyButton) {
            const original = this.selectionCopyButton.textContent;
            this.selectionCopyButton.textContent = "Copied";
            window.setTimeout(() => {
                this.selectionCopyButton.textContent = original;
            }, 900);
        }
    }

    attachPendingSelectionToAsk() {
        const pending = this.pendingSelection;

        if (!pending || !pending.text || pending.text.length > 5000) {
            return;
        }

        this.clearAttachedHighlightOnly();

        this.attachedContext = {
            text: pending.text,
            page: pending.page,
            section: pending.section || "",
        };

        pending.spans.forEach((span) => {
            span.classList.add("db-user-context-highlight");
        });

        if (this.selectedContextInput) {
            this.selectedContextInput.value = this.attachedContext.text;
        }

        if (this.selectedContextPageInput) {
            this.selectedContextPageInput.value = String(this.attachedContext.page);
        }

        if (this.selectedContextSectionInput) {
            this.selectedContextSectionInput.value = this.attachedContext.section;
        }

        if (this.selectedContextLocation) {
            const section = this.attachedContext.section
                ? ` · ${this.attachedContext.section}`
                : "";
            this.selectedContextLocation.textContent = (
                `Page ${this.attachedContext.page}${section}`
            );
        }

        if (this.selectedContextPreview) {
            this.selectedContextPreview.textContent = this.attachedContext.text;
        }

        if (this.selectedContextCard) {
            this.selectedContextCard.hidden = false;
        }

        window.getSelection()?.removeAllRanges();
        this.hideSelectionToolbar();
        this.pendingSelection = null;

        this.close();

        if (this.askTab) {
            this.askTab.click();
        }

        window.setTimeout(() => {
            this.selectedContextCard?.scrollIntoView({
                behavior: "smooth",
                block: "center",
            });
            this.askInput?.focus();
        }, 80);
    }

    clearAttachedHighlightOnly() {
        this.textLayer?.querySelectorAll(".db-user-context-highlight").forEach((span) => {
            span.classList.remove("db-user-context-highlight");
        });
    }

    clearAttachedContext() {
        this.attachedContext = null;
        this.pendingSelection = null;
        this.clearAttachedHighlightOnly();

        if (this.selectedContextInput) {
            this.selectedContextInput.value = "";
        }
        if (this.selectedContextPageInput) {
            this.selectedContextPageInput.value = "";
        }
        if (this.selectedContextSectionInput) {
            this.selectedContextSectionInput.value = "";
        }
        if (this.selectedContextPreview) {
            this.selectedContextPreview.textContent = "";
        }
        if (this.selectedContextCard) {
            this.selectedContextCard.hidden = true;
        }

        this.applyAttachedContextHighlightForCurrentPage();
    }

    applyAttachedContextHighlightForCurrentPage() {
        this.clearAttachedHighlightOnly();

        if (
            !this.attachedContext
            || this.attachedContext.page !== this.currentPage
        ) {
            return;
        }

        const pageTokens = this.buildPageTokenMap();
        const targetWords = tokenizeWords(this.attachedContext.text);
        const range = findBestTokenRange(pageTokens, targetWords);

        if (!range) {
            return;
        }

        const spans = new Set();

        for (let index = range.start; index <= range.end; index += 1) {
            spans.add(pageTokens[index].span);
        }

        spans.forEach((span) => {
            span.classList.add("db-user-context-highlight");
        });
    }

    changeZoom(delta) {
        this.fitWidth = false;
        this.scale = clamp(
            this.scale + delta,
            ZOOM_MIN,
            ZOOM_MAX
        );
        this.renderCurrentPage();
    }

    rotate(delta) {
        this.rotation = (this.rotation + delta + 360) % 360;
        this.renderCurrentPage();
    }

    updateZoomLabel() {
        if (this.fitWidth) {
            this.zoomLabel.textContent = "Fit width";
            return;
        }
        this.zoomLabel.textContent = `${Math.round(this.scale * 100)}%`;
    }

    setSidebarVisible(visible) {
        this.sidebarVisible = visible;
        this.workspace.classList.toggle("is-sidebar-hidden", !visible);
        this.sidebarToggle.setAttribute("aria-pressed", String(visible));

        if (this.fitWidth) {
            window.setTimeout(() => this.renderCurrentPage(), 80);
        }
    }

    activateSidebarView(view) {
        this.modal.querySelectorAll("[data-db-pdf-sidebar-view]").forEach((button) => {
            button.classList.toggle(
                "is-active",
                button.dataset.dbPdfSidebarView === view
            );
        });

        this.modal.querySelectorAll("[data-db-pdf-sidebar-panel]").forEach((panel) => {
            panel.classList.toggle(
                "is-active",
                panel.dataset.dbPdfSidebarPanel === view
            );
        });

        if (view === "find") {
            window.setTimeout(() => this.findInput?.focus(), 0);
        }
    }

    createThumbnailShells() {
        this.thumbnails.innerHTML = "";
        this.thumbnailObserver?.disconnect();

        this.thumbnailObserver = new IntersectionObserver(
            (entries) => {
                entries.forEach((entry) => {
                    if (!entry.isIntersecting) {
                        return;
                    }
                    const button = entry.target;
                    this.renderThumbnail(button);
                    this.thumbnailObserver.unobserve(button);
                });
            },
            {
                root: this.thumbnails,
                rootMargin: "260px 0px",
            }
        );

        for (let pageNumber = 1; pageNumber <= this.pdfDocument.numPages; pageNumber += 1) {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "db-pdf-thumbnail";
            button.dataset.page = String(pageNumber);
            button.innerHTML = `
                <span class="db-pdf-thumbnail-canvas-wrap">
                    <canvas></canvas>
                </span>
                <span>Page ${pageNumber}</span>
            `;
            button.addEventListener("click", () => this.goToPage(pageNumber));
            this.thumbnails.appendChild(button);
            this.thumbnailObserver.observe(button);
        }
    }

    async renderThumbnail(button) {
        if (button.dataset.rendered === "1") {
            return;
        }

        button.dataset.rendered = "1";
        const pageNumber = Number.parseInt(button.dataset.page, 10);

        try {
            const page = await this.pdfDocument.getPage(pageNumber);
            const baseViewport = page.getViewport({ scale: 1 });
            const scale = THUMBNAIL_WIDTH / baseViewport.width;
            const viewport = page.getViewport({ scale });
            const canvas = button.querySelector("canvas");
            const context = canvas.getContext("2d", { alpha: false });
            const outputScale = Math.min(window.devicePixelRatio || 1, 2);

            canvas.width = Math.floor(viewport.width * outputScale);
            canvas.height = Math.floor(viewport.height * outputScale);
            canvas.style.width = `${Math.floor(viewport.width)}px`;
            canvas.style.height = `${Math.floor(viewport.height)}px`;

            await page.render({
                canvasContext: context,
                viewport,
                transform: outputScale !== 1
                    ? [outputScale, 0, 0, outputScale, 0, 0]
                    : null,
            }).promise;
        } catch (error) {
            console.warn(`Could not render PDF thumbnail ${pageNumber}.`, error);
            button.classList.add("has-thumbnail-error");
        }
    }

    updateActiveThumbnail() {
        this.thumbnails.querySelectorAll(".db-pdf-thumbnail").forEach((button) => {
            const active = Number.parseInt(button.dataset.page, 10) === this.currentPage;
            button.classList.toggle("is-active", active);
            button.setAttribute("aria-current", active ? "page" : "false");

            if (active && this.sidebarVisible) {
                button.scrollIntoView({ block: "nearest" });
            }
        });
    }

    async getPageText(pageNumber) {
        if (this.textCache.has(pageNumber)) {
            return this.textCache.get(pageNumber);
        }

        const page = await this.pdfDocument.getPage(pageNumber);
        const content = await page.getTextContent();
        const text = content.items
            .map((item) => item.str || "")
            .join(" ")
            .replace(/\s+/g, " ")
            .trim();

        this.textCache.set(pageNumber, text);
        return text;
    }

    openNewTab() {
        const page = Math.max(1, this.currentPage);
        window.open(
            `${this.pdfUrl}#page=${page}`,
            "_blank",
            "noopener,noreferrer"
        );
    }

    download() {
        const anchor = document.createElement("a");
        anchor.href = joinUrl(this.pdfUrl, "download=1");
        anchor.download = this.documentName;
        anchor.hidden = true;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        this.setStatus("Download started");
    }

    print() {
        const frame = document.createElement("iframe");
        frame.className = "db-pdf-print-frame";
        frame.src = this.pdfUrl;
        frame.title = "Print PDF";
        document.body.appendChild(frame);

        const cleanup = () => {
            window.setTimeout(() => frame.remove(), 1500);
        };

        frame.addEventListener("load", () => {
            try {
                frame.contentWindow.focus();
                frame.contentWindow.print();
            } catch (error) {
                console.warn("Embedded PDF print was unavailable.", error);
                this.openNewTab();
            } finally {
                cleanup();
            }
        }, { once: true });

        window.setTimeout(() => {
            if (document.body.contains(frame)) {
                frame.remove();
            }
        }, 60000);
    }

    activateNativeFallback(page, error) {
        this.fallbackActive = true;
        this.currentPage = Math.max(1, page);
        this.showLoading(false);
        this.progress.hidden = true;
        this.workspace.hidden = true;
        this.nativeFallback.hidden = false;
        this.fallbackFrame.src = `${this.pdfUrl}#page=${this.currentPage}&view=FitH`;
        this.setStatus("Browser PDF viewer fallback");

        if (this.errorMessage && error?.message) {
            this.errorMessage.textContent = error.message;
        }
    }

    showLoading(visible) {
        this.loading.hidden = !visible;
    }

    showError(visible, message = "") {
        this.error.hidden = !visible;
        if (visible && message) {
            this.errorMessage.textContent = message;
        }
    }

    setStatus(message) {
        if (this.status) {
            this.status.textContent = message;
        }
    }

    handleKeyboard(event) {
        if (!this.isOpen()) {
            return;
        }

        if (event.key === "Escape") {
            event.preventDefault();

            if (this.selectionToolbar && !this.selectionToolbar.hidden) {
                this.hideSelectionToolbar();
                window.getSelection()?.removeAllRanges();
                return;
            }

            this.close();
            return;
        }

        if ((event.ctrlKey || event.metaKey) && event.key.toLocaleLowerCase() === "f") {
            event.preventDefault();
            this.setSidebarVisible(true);
            this.activateSidebarView("find");
            return;
        }

        const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(
            document.activeElement?.tagName
        );

        if (typing) {
            return;
        }

        if (event.key === "ArrowLeft" || event.key === "PageUp") {
            event.preventDefault();
            this.goToPage(this.currentPage - 1);
        } else if (event.key === "ArrowRight" || event.key === "PageDown") {
            event.preventDefault();
            this.goToPage(this.currentPage + 1);
        } else if (event.key === "+" || event.key === "=") {
            event.preventDefault();
            this.changeZoom(ZOOM_STEP);
        } else if (event.key === "-") {
            event.preventDefault();
            this.changeZoom(-ZOOM_STEP);
        }
    }
}

function initPDFViewer() {
    const modal = document.querySelector("[data-db-pdf-modal]");
    if (!modal) {
        return;
    }

    const viewer = new LifeOSPDFViewer(modal);
    const parameters = new URLSearchParams(window.location.search);
    const requestedPage = parameters.get("pdf_page");

    if (requestedPage) {
        window.requestAnimationFrame(() => {
            viewer.open(parsePage(requestedPage));
        });
    }
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initPDFViewer, { once: true });
} else {
    initPDFViewer();
}
