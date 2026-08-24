(function () {
    "use strict";

    function onReady(callback) {
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", callback);
            return;
        }

        callback();
    }

    function normalize(value) {
        return String(value || "")
            .trim()
            .toLowerCase();
    }

    function setPressed(buttons, activeButton) {
        buttons.forEach(function (button) {
            const active = button === activeButton;

            button.classList.toggle(
                "is-active",
                active
            );

            button.setAttribute(
                "aria-pressed",
                active ? "true" : "false"
            );
        });
    }

    function formatBytes(bytes) {
        const number = Number(bytes) || 0;

        if (number < 1024) {
            return number + " B";
        }

        if (number < 1024 * 1024) {
            return (
                (number / 1024).toFixed(1)
                + " KB"
            );
        }

        return (
            (number / (1024 * 1024)).toFixed(1)
            + " MB"
        );
    }

    function initUploadForm() {
        const form = document.querySelector(
            "[data-db-upload-form]"
        );

        if (!form) {
            return;
        }

        const input = form.querySelector(
            "[data-db-file-input]"
        );

        const dropzone = form.querySelector(
            "[data-db-dropzone]"
        );

        const projectSelect = form.querySelector(
            "[data-db-project-select]"
        );

        const selectedFile = form.querySelector(
            "[data-db-selected-file]"
        );

        const selectedName = form.querySelector(
            "[data-db-selected-name]"
        );

        const selectedSize = form.querySelector(
            "[data-db-selected-size]"
        );

        const clearButton = form.querySelector(
            "[data-db-clear-file]"
        );

        const errorMessage = form.querySelector(
            "[data-db-upload-error]"
        );

        const submitButton = form.querySelector(
            "[data-db-upload-submit]"
        );

        const dropzoneTitle = form.querySelector(
            "[data-db-dropzone-title]"
        );

        const dropzoneMessage = form.querySelector(
            "[data-db-dropzone-message]"
        );

        if (
            !input
            || !dropzone
            || !submitButton
        ) {
            return;
        }

        const maxBytes = Number(
            dropzone.dataset.maxBytes
        ) || 25 * 1024 * 1024;

        let validFile = null;

        function showError(message) {
            if (!errorMessage) {
                return;
            }

            errorMessage.textContent = message;
            errorMessage.hidden = !message;
        }

        function updateSubmitState() {
            const hasProject = (
                !projectSelect
                || Boolean(projectSelect.value)
            );

            submitButton.disabled = !(
                validFile
                && hasProject
            );
        }

        function resetFile() {
            validFile = null;
            input.value = "";

            if (selectedFile) {
                selectedFile.hidden = true;
            }

            dropzone.classList.remove(
                "has-file",
                "has-error"
            );

            if (dropzoneTitle) {
                dropzoneTitle.textContent =
                    "Drop a PDF here or browse";
            }

            if (dropzoneMessage) {
                dropzoneMessage.textContent =
                    "The original filename is shown in LifeOS while storage uses a private, unique key.";
            }

            showError("");
            updateSubmitState();
        }

        function validateFile(file) {
            if (!file) {
                resetFile();
                return false;
            }

            const filename = normalize(file.name);
            const mimeType = normalize(file.type);

            const isPdf = (
                filename.endsWith(".pdf")
                || mimeType === "application/pdf"
            );

            if (!isPdf) {
                validFile = null;
                dropzone.classList.add("has-error");

                showError(
                    "Choose a PDF file. Other file types are not supported."
                );

                updateSubmitState();
                return false;
            }

            if (file.size > maxBytes) {
                validFile = null;
                dropzone.classList.add("has-error");

                showError(
                    "This PDF is "
                    + formatBytes(file.size)
                    + ". The upload limit is "
                    + formatBytes(maxBytes)
                    + "."
                );

                updateSubmitState();
                return false;
            }

            validFile = file;

            dropzone.classList.remove(
                "has-error"
            );

            dropzone.classList.add(
                "has-file"
            );

            showError("");

            if (selectedFile) {
                selectedFile.hidden = false;
            }

            if (selectedName) {
                selectedName.textContent = file.name;
            }

            if (selectedSize) {
                selectedSize.textContent = (
                    formatBytes(file.size)
                    + " · PDF"
                );
            }

            if (dropzoneTitle) {
                dropzoneTitle.textContent =
                    "PDF ready to upload";
            }

            if (dropzoneMessage) {
                dropzoneMessage.textContent =
                    "Choose another file by dropping it here.";
            }

            updateSubmitState();
            return true;
        }

        input.addEventListener(
            "change",
            function () {
                validateFile(
                    input.files
                    && input.files[0]
                );
            }
        );

        [
            "dragenter",
            "dragover"
        ].forEach(function (eventName) {
            dropzone.addEventListener(
                eventName,
                function (event) {
                    event.preventDefault();
                    dropzone.classList.add(
                        "is-dragging"
                    );
                }
            );
        });

        [
            "dragleave",
            "drop"
        ].forEach(function (eventName) {
            dropzone.addEventListener(
                eventName,
                function (event) {
                    event.preventDefault();
                    dropzone.classList.remove(
                        "is-dragging"
                    );
                }
            );
        });

        dropzone.addEventListener(
            "drop",
            function (event) {
                const files = (
                    event.dataTransfer
                    && event.dataTransfer.files
                );

                if (!files || !files.length) {
                    return;
                }

                const file = files[0];

                if (validateFile(file)) {
                    try {
                        const transfer =
                            new DataTransfer();

                        transfer.items.add(file);
                        input.files = transfer.files;
                    } catch (error) {
                        console.warn(
                            "The dropped file could not be assigned to the input.",
                            error
                        );
                    }
                }
            }
        );

        if (clearButton) {
            clearButton.addEventListener(
                "click",
                resetFile
            );
        }

        if (projectSelect) {
            projectSelect.addEventListener(
                "change",
                updateSubmitState
            );
        }

        form.addEventListener(
            "submit",
            function (event) {
                if (
                    !validFile
                    || (
                        projectSelect
                        && !projectSelect.value
                    )
                ) {
                    event.preventDefault();

                    showError(
                        !validFile
                            ? "Choose a valid PDF before uploading."
                            : "Select the project that owns this document."
                    );

                    return;
                }

                submitButton.disabled = true;
                submitButton.textContent =
                    "Preparing PDF…";
            }
        );

        updateSubmitState();
    }

    function initDocumentLibrary() {
        const library = document.querySelector(
            "[data-db-library]"
        );

        if (!library) {
            return;
        }

        const container = library.querySelector(
            "[data-db-document-container]"
        );

        if (!container) {
            return;
        }

        const searchInput = library.querySelector(
            "[data-db-document-search]"
        );

        const projectFilter = library.querySelector(
            "[data-db-project-filter]"
        );

        const statusFilter = library.querySelector(
            "[data-db-status-filter]"
        );

        const sortSelect = library.querySelector(
            "[data-db-sort]"
        );

        const count = library.querySelector(
            "[data-db-visible-count]"
        );

        const empty = library.querySelector(
            "[data-db-filter-empty]"
        );

        const reset = library.querySelector(
            "[data-db-reset-filters]"
        );

        const viewButtons = Array.from(
            library.querySelectorAll(
                "[data-db-view]"
            )
        );

        const cards = Array.from(
            container.querySelectorAll(
                "[data-db-document-card]"
            )
        );

        let view = "grid";

        try {
            view = (
                localStorage.getItem(
                    "lifeos-document-view"
                )
                || "grid"
            );
        } catch (error) {
            view = "grid";
        }

        if (!["grid", "list"].includes(view)) {
            view = "grid";
        }

        function applyView(nextView) {
            view = nextView;
            container.dataset.view = view;

            viewButtons.forEach(function (button) {
                const active = (
                    button.dataset.dbView === view
                );

                button.classList.toggle(
                    "is-active",
                    active
                );

                button.setAttribute(
                    "aria-pressed",
                    active ? "true" : "false"
                );
            });

            try {
                localStorage.setItem(
                    "lifeos-document-view",
                    view
                );
            } catch (error) {
                // Storage is an enhancement, not a requirement.
            }
        }

        function sortCards() {
            const mode = (
                sortSelect
                ? sortSelect.value
                : "newest"
            );

            const sorted = cards.slice().sort(
                function (first, second) {
                    if (mode === "name") {
                        return first.dataset.name.localeCompare(
                            second.dataset.name
                        );
                    }

                    if (mode === "project") {
                        return first.dataset.project.localeCompare(
                            second.dataset.project
                        );
                    }

                    const firstDate = Date.parse(
                        first.dataset.date
                    ) || 0;

                    const secondDate = Date.parse(
                        second.dataset.date
                    ) || 0;

                    if (mode === "oldest") {
                        return firstDate - secondDate;
                    }

                    return secondDate - firstDate;
                }
            );

            sorted.forEach(function (card) {
                container.appendChild(card);
            });
        }

        function applyFilters() {
            const query = normalize(
                searchInput
                && searchInput.value
            );

            const project = normalize(
                projectFilter
                && projectFilter.value
            ) || "all";

            const status = normalize(
                statusFilter
                && statusFilter.value
            ) || "all";

            let visible = 0;

            cards.forEach(function (card) {
                const matchesQuery = (
                    !query
                    || normalize(
                        card.dataset.search
                    ).includes(query)
                );

                const matchesProject = (
                    project === "all"
                    || normalize(
                        card.dataset.project
                    ) === project
                );

                const matchesStatus = (
                    status === "all"
                    || normalize(
                        card.dataset.status
                    ) === status
                );

                const show = (
                    matchesQuery
                    && matchesProject
                    && matchesStatus
                );

                card.hidden = !show;

                if (show) {
                    visible += 1;
                }
            });

            if (count) {
                count.textContent = String(visible);
            }

            if (empty) {
                empty.hidden = visible !== 0;
            }
        }

        [
            searchInput,
            projectFilter,
            statusFilter
        ].forEach(function (control) {
            if (!control) {
                return;
            }

            control.addEventListener(
                control.tagName === "INPUT"
                    ? "input"
                    : "change",
                applyFilters
            );
        });

        if (sortSelect) {
            sortSelect.addEventListener(
                "change",
                function () {
                    sortCards();
                    applyFilters();
                }
            );
        }

        viewButtons.forEach(function (button) {
            button.addEventListener(
                "click",
                function () {
                    applyView(
                        button.dataset.dbView
                    );
                }
            );
        });

        if (reset) {
            reset.addEventListener(
                "click",
                function () {
                    if (searchInput) {
                        searchInput.value = "";
                    }

                    if (projectFilter) {
                        projectFilter.value = "all";
                    }

                    if (statusFilter) {
                        statusFilter.value = "all";
                    }

                    if (sortSelect) {
                        sortSelect.value = "newest";
                    }

                    sortCards();
                    applyFilters();

                    if (searchInput) {
                        searchInput.focus();
                    }
                }
            );
        }

        applyView(view);
        sortCards();
        applyFilters();
    }

    function initTabs() {
        const detail = document.querySelector(
            "[data-db-detail]"
        );

        if (!detail) {
            return;
        }

        const tabs = Array.from(
            detail.querySelectorAll(
                "[data-db-tab]"
            )
        );

        const panels = Array.from(
            detail.querySelectorAll(
                "[data-db-panel]"
            )
        );

        if (!tabs.length || !panels.length) {
            return;
        }

        function normalizePanelName(value) {
            const cleaned = normalize(value);

            if (
                cleaned === "ask-document"
                || cleaned === "ask"
            ) {
                return "ask";
            }

            if (
                [
                    "overview",
                    "insights",
                    "search",
                    "actions"
                ].includes(
                    cleaned
                )
            ) {
                return cleaned;
            }

            return "overview";
        }

        function activate(
            panelName,
            options
        ) {
            const config = options || {};
            const normalized = normalizePanelName(
                panelName
            );

            tabs.forEach(function (tab) {
                const active = (
                    tab.dataset.dbTab === normalized
                );

                tab.classList.toggle(
                    "is-active",
                    active
                );

                tab.setAttribute(
                    "aria-selected",
                    active ? "true" : "false"
                );

                tab.tabIndex = active ? 0 : -1;
            });

            panels.forEach(function (panel) {
                const active = (
                    panel.dataset.dbPanel
                    === normalized
                );

                panel.classList.toggle(
                    "is-active",
                    active
                );

                panel.hidden = !active;
            });

            if (config.updateHash !== false) {
                const activeTab = tabs.find(
                    function (tab) {
                        return (
                            tab.dataset.dbTab
                            === normalized
                        );
                    }
                );

                const nextHash = (
                    activeTab
                    && activeTab.dataset.dbHash
                ) || normalized;

                if (
                    window.location.hash
                    !== "#" + nextHash
                ) {
                    history.replaceState(
                        null,
                        "",
                        "#" + nextHash
                    );
                }
            }

            if (config.focus) {
                const activeTab = tabs.find(
                    function (tab) {
                        return (
                            tab.dataset.dbTab
                            === normalized
                        );
                    }
                );

                if (activeTab) {
                    activeTab.focus();
                }
            }

            return normalized;
        }

        tabs.forEach(function (tab, index) {
            tab.addEventListener(
                "click",
                function () {
                    activate(
                        tab.dataset.dbTab,
                        {
                            updateHash: true,
                            focus: false
                        }
                    );
                }
            );

            tab.addEventListener(
                "keydown",
                function (event) {
                    if (
                        ![
                            "ArrowLeft",
                            "ArrowRight",
                            "Home",
                            "End"
                        ].includes(event.key)
                    ) {
                        return;
                    }

                    event.preventDefault();

                    let nextIndex = index;

                    if (event.key === "ArrowLeft") {
                        nextIndex = (
                            index - 1 + tabs.length
                        ) % tabs.length;
                    }

                    if (event.key === "ArrowRight") {
                        nextIndex = (
                            index + 1
                        ) % tabs.length;
                    }

                    if (event.key === "Home") {
                        nextIndex = 0;
                    }

                    if (event.key === "End") {
                        nextIndex = tabs.length - 1;
                    }

                    activate(
                        tabs[nextIndex].dataset.dbTab,
                        {
                            updateHash: true,
                            focus: true
                        }
                    );
                }
            );
        });

        detail
            .querySelectorAll(
                "[data-db-tab-jump]"
            )
            .forEach(function (trigger) {
                trigger.addEventListener(
                    "click",
                    function () {
                        const panel = activate(
                            trigger.dataset.dbTabJump,
                            {
                                updateHash: true,
                                focus: false
                            }
                        );

                        const targetId = (
                            trigger.dataset.dbScrollTarget
                        );

                        if (targetId) {
                            window.setTimeout(
                                function () {
                                    const target =
                                        document.getElementById(
                                            targetId
                                        );

                                    if (target) {
                                        target.open = true;

                                        target.scrollIntoView(
                                            {
                                                behavior: "smooth",
                                                block: "start"
                                            }
                                        );
                                    }
                                },
                                50
                            );
                        } else if (panel === "ask") {
                            window.setTimeout(
                                function () {
                                    const input =
                                        detail.querySelector(
                                            "[data-db-question-input]"
                                        );

                                    if (input) {
                                        input.focus();
                                    }
                                },
                                50
                            );
                        } else if (panel === "search") {
                            window.setTimeout(
                                function () {
                                    const input =
                                        detail.querySelector(
                                            "[data-db-document-search-input]"
                                        );

                                    if (input) {
                                        input.focus();
                                    }
                                },
                                50
                            );
                        }
                    }
                );
            });

        function activateFromHash() {
            const hash = window.location.hash
                .replace(/^#/, "");

            const initialPanel = (
                hash
                || detail.dataset.dbInitialTab
                || "overview"
            );

            activate(
                initialPanel,
                {
                    updateHash: false,
                    focus: false
                }
            );

            if (hash === "ask-document") {
                const ask = document.getElementById(
                    "ask-document"
                );

                if (ask) {
                    window.setTimeout(
                        function () {
                            ask.scrollIntoView(
                                {
                                    block: "start"
                                }
                            );
                        },
                        20
                    );
                }
            }
        }

        window.addEventListener(
            "hashchange",
            activateFromHash
        );

        activateFromHash();
    }

    function autoResizeTextarea(textarea) {
        textarea.style.height = "auto";

        textarea.style.height = (
            Math.min(
                textarea.scrollHeight,
                260
            )
            + "px"
        );
    }

    function initQuestionComposer() {
        const input = document.querySelector(
            "[data-db-question-input]"
        );

        if (!input) {
            return;
        }

        const form = input.closest(
            "[data-db-question-form]"
        );

        const count = document.querySelector(
            "[data-db-character-count]"
        );

        const maximum = Number(
            input.getAttribute("maxlength")
        ) || 2000;

        function updateCount() {
            if (count) {
                count.textContent = (
                    input.value.length
                    + " / "
                    + maximum
                );

                count.classList.toggle(
                    "is-near-limit",
                    input.value.length
                    >= maximum * 0.9
                );
            }

            autoResizeTextarea(input);
        }

        document
            .querySelectorAll(
                "[data-db-question-suggestion]"
            )
            .forEach(function (button) {
                button.addEventListener(
                    "click",
                    function () {
                        input.value = (
                            button.dataset
                                .dbQuestionSuggestion
                            || ""
                        );

                        updateCount();
                        input.focus();
                    }
                );
            });

        document
            .querySelectorAll(
                "[data-db-reask]"
            )
            .forEach(function (button) {
                button.addEventListener(
                    "click",
                    function () {
                        input.value = (
                            button.dataset.dbReask
                            || ""
                        );

                        updateCount();
                        input.focus();

                        input.scrollIntoView(
                            {
                                behavior: "smooth",
                                block: "center"
                            }
                        );
                    }
                );
            });

        input.addEventListener(
            "input",
            updateCount
        );

        if (form) {
            form.addEventListener(
                "submit",
                function () {
                    const button = form.querySelector(
                        "button[type='submit']"
                    );

                    if (button) {
                        button.disabled = true;
                        button.textContent =
                            "Searching document…";
                    }
                }
            );
        }

        updateCount();
    }

    function initCopyButtons() {
        const buttons = document.querySelectorAll(
            "[data-db-copy-target]"
        );

        buttons.forEach(function (button) {
            button.addEventListener(
                "click",
                async function () {
                    const target = document.getElementById(
                        button.dataset.dbCopyTarget
                    );

                    if (!target) {
                        return;
                    }

                    const value = (
                        target.innerText
                        || target.textContent
                        || ""
                    ).trim();

                    if (!value) {
                        return;
                    }

                    const original =
                        button.textContent;

                    try {
                        if (
                            navigator.clipboard
                            && window.isSecureContext
                        ) {
                            await navigator.clipboard.writeText(
                                value
                            );
                        } else {
                            const helper =
                                document.createElement(
                                    "textarea"
                                );

                            helper.value = value;
                            helper.setAttribute(
                                "readonly",
                                ""
                            );

                            helper.style.position =
                                "fixed";

                            helper.style.opacity =
                                "0";

                            document.body.appendChild(
                                helper
                            );

                            helper.select();

                            document.execCommand(
                                "copy"
                            );

                            helper.remove();
                        }

                        button.textContent = "Copied";
                        button.classList.add(
                            "is-copied"
                        );
                    } catch (error) {
                        button.textContent =
                            "Copy failed";
                    }

                    window.setTimeout(
                        function () {
                            button.textContent =
                                original;

                            button.classList.remove(
                                "is-copied"
                            );
                        },
                        1600
                    );
                }
            );
        });
    }

    function initInsightSearch() {
        const input = document.querySelector(
            "[data-db-insight-search]"
        );

        if (!input) {
            return;
        }

        const groups = Array.from(
            document.querySelectorAll(
                "[data-db-insight-group]"
            )
        );

        const items = Array.from(
            document.querySelectorAll(
                "[data-db-insight-item]"
            )
        );

        const empty = document.querySelector(
            "[data-db-insight-empty]"
        );

        function apply() {
            const query = normalize(
                input.value
            );

            let totalVisible = 0;

            items.forEach(function (item) {
                const show = (
                    !query
                    || normalize(
                        item.dataset.search
                    ).includes(query)
                );

                item.hidden = !show;

                if (show) {
                    totalVisible += 1;
                }
            });

            groups.forEach(function (group) {
                const visible = (
                    group.querySelectorAll(
                        "[data-db-insight-item]:not([hidden])"
                    ).length
                );

                group.hidden = visible === 0;

                if (query && visible > 0) {
                    group.open = true;
                }
            });

            if (empty) {
                empty.hidden = totalVisible !== 0;
            }
        }

        input.addEventListener(
            "input",
            apply
        );

        apply();
    }

    function initActionFilters() {
        const buttons = Array.from(
            document.querySelectorAll(
                "[data-db-action-filter]"
            )
        );

        const cards = Array.from(
            document.querySelectorAll(
                "[data-db-action-card]"
            )
        );

        if (!buttons.length || !cards.length) {
            return;
        }

        const count = document.querySelector(
            "[data-db-action-count]"
        );

        const empty = document.querySelector(
            "[data-db-action-empty]"
        );

        function apply(filter) {
            let visible = 0;

            cards.forEach(function (card) {
                const show = (
                    filter === "all"
                    || card.dataset.actionStatus
                    === filter
                );

                card.hidden = !show;

                if (show) {
                    visible += 1;
                }
            });

            if (count) {
                count.textContent = String(visible);
            }

            if (empty) {
                empty.hidden = visible !== 0;
            }
        }

        buttons.forEach(function (button) {
            button.addEventListener(
                "click",
                function () {
                    setPressed(
                        buttons,
                        button
                    );

                    apply(
                        button.dataset.dbActionFilter
                    );
                }
            );
        });

        apply("all");
    }

    function initQuestionHistory() {
        const cards = Array.from(
            document.querySelectorAll(
                "[data-db-question-card]"
            )
        );

        if (!cards.length) {
            return;
        }

        const input = document.querySelector(
            "[data-db-question-search]"
        );

        const buttons = Array.from(
            document.querySelectorAll(
                "[data-db-question-filter]"
            )
        );

        const count = document.querySelector(
            "[data-db-question-count]"
        );

        const empty = document.querySelector(
            "[data-db-question-empty]"
        );

        let filter = "all";

        function apply() {
            const query = normalize(
                input
                && input.value
            );

            let visible = 0;

            cards.forEach(function (card) {
                const matchesSearch = (
                    !query
                    || normalize(
                        card.dataset.search
                    ).includes(query)
                );

                const questionStatus = (
                    card.dataset.questionStatus
                    || ""
                );

                const matchesStatus = (
                    filter === "all"
                    || questionStatus === filter
                    || (
                        filter === "completed"
                        && [
                            "historical",
                            "outdated",
                        ].includes(questionStatus)
                    )
                );

                const show = (
                    matchesSearch
                    && matchesStatus
                );

                card.hidden = !show;

                if (show) {
                    visible += 1;
                }
            });

            if (count) {
                count.textContent = String(visible);
            }

            if (empty) {
                empty.hidden = visible !== 0;
            }
        }

        if (input) {
            input.addEventListener(
                "input",
                apply
            );
        }

        buttons.forEach(function (button) {
            button.addEventListener(
                "click",
                function () {
                    filter = (
                        button.dataset.dbQuestionFilter
                        || "all"
                    );

                    setPressed(
                        buttons,
                        button
                    );

                    apply();
                }
            );
        });

        apply();
    }

    function initDocumentTypeConfirmation() {
        const panel = document.querySelector(
            "[data-db-type-confirmation]"
        );

        const reviewButtons = Array.from(
            document.querySelectorAll(
                "[data-db-type-review]"
            )
        );

        function revealPanel() {
            if (!panel) {
                return;
            }

            panel.scrollIntoView({
                behavior: "smooth",
                block: "center"
            });

            const select = panel.querySelector(
                "[data-db-type-select]"
            );

            if (select) {
                window.setTimeout(
                    function () {
                        select.focus({
                            preventScroll: true
                        });
                    },
                    350
                );
            }
        }

        reviewButtons.forEach(function (button) {
            button.addEventListener(
                "click",
                revealPanel
            );
        });

        if (!panel) {
            return;
        }

        const select = panel.querySelector(
            "[data-db-type-select]"
        );

        const note = panel.querySelector(
            "[data-db-type-choice-note]"
        );

        const detectedType = (
            panel.dataset.dbDetectedType
            || ""
        );

        if (!select || !note) {
            return;
        }

        function updateChoiceMessage() {
            const option = select.options[
                select.selectedIndex
            ];

            if (!option) {
                return;
            }

            const selectedLabel = (
                option.textContent
                || ""
            ).trim();

            if (select.value === detectedType) {
                note.textContent = (
                    "You are confirming LifeOS's detected type: "
                    + selectedLabel
                    + "."
                );

                panel.classList.remove(
                    "has-user-override"
                );

                return;
            }

            note.textContent = (
                "You changed the analysis type to "
                + selectedLabel
                + ". LifeOS will use your choice for the next analysis."
            );

            panel.classList.add(
                "has-user-override"
            );
        }

        select.addEventListener(
            "change",
            updateChoiceMessage
        );

        updateChoiceMessage();
    }

    function initDocumentPassageSearch() {
        const form = document.querySelector(
            "[data-db-passage-search-form]"
        );

        if (!form) {
            return;
        }

        const input = form.querySelector(
            "[data-db-document-search-input]"
        );

        const clearButton = form.querySelector(
            "[data-db-document-search-clear]"
        );

        if (!input) {
            return;
        }

        function updateClearState() {
            if (!clearButton) {
                return;
            }

            clearButton.hidden = !input.value.trim();
        }

        input.addEventListener(
            "input",
            updateClearState
        );

        if (clearButton) {
            clearButton.addEventListener(
                "click",
                function () {
                    input.value = "";
                    updateClearState();
                    input.focus();
                }
            );
        }

        form.addEventListener(
            "submit",
            function (event) {
                const cleaned = input.value.trim();

                if (!cleaned) {
                    event.preventDefault();
                    input.focus();
                    return;
                }

                input.value = cleaned;

                const button = form.querySelector(
                    "button[type='submit']"
                );

                if (button) {
                    button.disabled = true;
                    button.dataset.originalLabel =
                        button.textContent.trim();
                    button.textContent = "Searching…";
                    button.classList.add("is-loading");
                }
            }
        );

        updateClearState();
    }

    function initInlineLoading() {
        document
            .querySelectorAll(
                "form[data-db-inline-loading]"
            )
            .forEach(function (form) {
                form.addEventListener(
                    "submit",
                    function () {
                        if (
                            form.hasAttribute("data-confirm")
                            && form.dataset.confirmApproved
                            !== "true"
                        ) {
                            return;
                        }

                        const button = form.querySelector(
                            "button[type='submit']"
                        );

                        if (!button) {
                            return;
                        }

                        button.dataset.originalLabel =
                            button.textContent.trim();

                        button.disabled = true;
                        button.classList.add(
                            "is-loading"
                        );

                        button.textContent =
                            "Working…";
                    }
                );
            });
    }

    onReady(function () {
        initUploadForm();
        initDocumentLibrary();
        initTabs();
        initQuestionComposer();
        initCopyButtons();
        initInsightSearch();
        initActionFilters();
        initQuestionHistory();
        initDocumentTypeConfirmation();
        initDocumentPassageSearch();
        initInlineLoading();
    });
})();
