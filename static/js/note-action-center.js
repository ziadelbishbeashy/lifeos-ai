(function () {
    "use strict";

    const root = document.querySelector("[data-note-action-center]");

    if (!root) {
        return;
    }

    const tabButtons = Array.from(
        root.querySelectorAll("[data-note-tab]")
    );

    const panels = Array.from(
        root.querySelectorAll("[data-note-panel]")
    );

    const hashToTab = {
        "#action-plan": "tasks",
        "#ask-lifeos": "ask",
        "#original-note": "original",
        "#lifeos-insight": "overview",
    };

    const tabToHash = {
        overview: "#lifeos-insight",
        tasks: "#action-plan",
        ask: "#ask-lifeos",
        original: "#original-note",
    };

    function activateTab(tabName, options = {}) {
        const { updateHash = false, focus = false } = options;

        const activeButton = tabButtons.find(
            (button) => button.dataset.noteTab === tabName
        );

        const activePanel = panels.find(
            (panel) => panel.dataset.notePanel === tabName
        );

        if (!activeButton || !activePanel) {
            return;
        }

        tabButtons.forEach((button) => {
            const isActive = button === activeButton;

            button.classList.toggle("is-active", isActive);
            button.setAttribute(
                "aria-selected",
                isActive ? "true" : "false"
            );
            button.tabIndex = isActive ? 0 : -1;
        });

        panels.forEach((panel) => {
            const isActive = panel === activePanel;

            panel.classList.toggle("is-active", isActive);
            panel.hidden = !isActive;
        });

        if (updateHash && tabToHash[tabName]) {
            window.history.replaceState(
                null,
                "",
                tabToHash[tabName]
            );
        }

        if (focus) {
            activeButton.focus();
        }
    }

    tabButtons.forEach((button, index) => {
        button.addEventListener("click", () => {
            activateTab(button.dataset.noteTab, {
                updateHash: true,
            });
        });

        button.addEventListener("keydown", (event) => {
            if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
                return;
            }

            event.preventDefault();

            let nextIndex = index;

            if (event.key === "ArrowRight") {
                nextIndex = (index + 1) % tabButtons.length;
            } else if (event.key === "ArrowLeft") {
                nextIndex = (
                    index - 1 + tabButtons.length
                ) % tabButtons.length;
            } else if (event.key === "Home") {
                nextIndex = 0;
            } else if (event.key === "End") {
                nextIndex = tabButtons.length - 1;
            }

            activateTab(
                tabButtons[nextIndex].dataset.noteTab,
                {
                    updateHash: true,
                    focus: true,
                }
            );
        });
    });

    root.querySelectorAll("[data-open-note-tab]").forEach((control) => {
        control.addEventListener("click", () => {
            const tabName = control.dataset.openNoteTab;

            activateTab(tabName, {
                updateHash: true,
            });

            const tabBar = root.querySelector(".note-tabs");

            if (tabBar) {
                tabBar.scrollIntoView({
                    behavior: "smooth",
                    block: "start",
                });
            }
        });
    });

    const questionField = root.querySelector("#noteQuestion");
    const questionCount = root.querySelector("#noteQuestionCount");

    function updateQuestionCount() {
        if (!questionField || !questionCount) {
            return;
        }

        questionCount.textContent = String(questionField.value.length);
    }

    if (questionField) {
        questionField.addEventListener("input", updateQuestionCount);
        updateQuestionCount();
    }

    root.querySelectorAll("[data-note-question]").forEach((control) => {
        control.addEventListener("click", () => {
            if (!questionField) {
                return;
            }

            activateTab("ask", {
                updateHash: true,
            });

            questionField.value = control.dataset.noteQuestion || "";
            updateQuestionCount();
            questionField.focus();

            questionField.scrollIntoView({
                behavior: "smooth",
                block: "center",
            });
        });
    });

    function appendInlineText(parent, text) {
        const parts = String(text).split(/(\*\*[^*]+\*\*|`[^`]+`)/g);

        parts.forEach((part) => {
            if (!part) {
                return;
            }

            if (part.startsWith("**") && part.endsWith("**")) {
                const strong = document.createElement("strong");
                strong.textContent = part.slice(2, -2);
                parent.appendChild(strong);
                return;
            }

            if (part.startsWith("`") && part.endsWith("`")) {
                const code = document.createElement("code");
                code.textContent = part.slice(1, -1);
                parent.appendChild(code);
                return;
            }

            parent.appendChild(document.createTextNode(part));
        });
    }

    function renderReadableText(element) {
        const rawText = element.textContent
            .replace(/\r\n/g, "\n")
            .trim();

        if (!rawText) {
            return;
        }

        const lines = rawText.split("\n");
        const fragment = document.createDocumentFragment();
        let paragraphLines = [];
        let activeList = null;
        let activeListType = null;

        function closeList() {
            activeList = null;
            activeListType = null;
        }

        function flushParagraph() {
            const text = paragraphLines.join(" ").trim();
            paragraphLines = [];

            if (!text) {
                return;
            }

            const paragraph = document.createElement("p");
            appendInlineText(paragraph, text);
            fragment.appendChild(paragraph);
        }

        lines.forEach((line) => {
            const trimmed = line.trim();

            if (!trimmed) {
                flushParagraph();
                closeList();
                return;
            }

            const bulletMatch = trimmed.match(/^[-*•]\s+(.+)$/);
            const numberMatch = trimmed.match(/^\d+[.)]\s+(.+)$/);
            const headingMatch = trimmed.match(/^#{1,4}\s+(.+)$/);

            if (headingMatch) {
                flushParagraph();
                closeList();

                const heading = document.createElement("h4");
                appendInlineText(heading, headingMatch[1]);
                fragment.appendChild(heading);
                return;
            }

            if (
                trimmed.length <= 72 &&
                trimmed.endsWith(":") &&
                !bulletMatch &&
                !numberMatch
            ) {
                flushParagraph();
                closeList();

                const heading = document.createElement("h4");
                appendInlineText(
                    heading,
                    trimmed.slice(0, -1)
                );
                fragment.appendChild(heading);
                return;
            }

            if (bulletMatch || numberMatch) {
                flushParagraph();

                const listType = numberMatch ? "ol" : "ul";

                if (!activeList || activeListType !== listType) {
                    activeList = document.createElement(listType);
                    activeListType = listType;
                    fragment.appendChild(activeList);
                }

                const item = document.createElement("li");
                appendInlineText(
                    item,
                    (bulletMatch || numberMatch)[1]
                );
                activeList.appendChild(item);
                return;
            }

            closeList();
            paragraphLines.push(trimmed);
        });

        flushParagraph();
        element.replaceChildren(fragment);
        element.classList.add("is-rendered");
    }

    root.querySelectorAll(".js-readable-text").forEach(
        renderReadableText
    );

    const initialTab = hashToTab[window.location.hash] || "overview";
    activateTab(initialTab);
})();
