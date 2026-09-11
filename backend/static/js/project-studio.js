/* =========================================================
   LifeOS Project Studio — Enhancement Sprint E5
   Project tab navigation and compact progress treatment.
   ========================================================= */

document.addEventListener("DOMContentLoaded", function () {
    "use strict";

    const tabButtons = Array.from(
        document.querySelectorAll("[data-project-studio-tab]")
    );

    const panels = Array.from(
        document.querySelectorAll("[data-project-studio-panel]")
    );

    if (tabButtons.length && panels.length) {
        function activateTab(tabName, updateHash = true) {
            const validTab = tabButtons.some(
                (button) => button.dataset.projectStudioTab === tabName
            );

            const nextTab = validTab ? tabName : "overview";

            tabButtons.forEach(function (button) {
                const isActive =
                    button.dataset.projectStudioTab === nextTab;

                button.classList.toggle("active", isActive);
                button.setAttribute(
                    "aria-selected",
                    isActive ? "true" : "false"
                );
            });

            panels.forEach(function (panel) {
                const isActive =
                    panel.dataset.projectStudioPanel === nextTab;

                panel.classList.toggle("active", isActive);
                panel.hidden = !isActive;
            });

            if (updateHash && window.history && window.history.replaceState) {
                const nextUrl = `${window.location.pathname}${window.location.search}#${nextTab}`;
                window.history.replaceState(null, "", nextUrl);
            }
        }

        tabButtons.forEach(function (button) {
            button.addEventListener("click", function () {
                activateTab(button.dataset.projectStudioTab);
            });
        });

        document
            .querySelectorAll("[data-open-project-tab]")
            .forEach(function (button) {
                button.addEventListener("click", function () {
                    const tabName = button.dataset.openProjectTab;
                    activateTab(tabName);

                    const tabs = document.querySelector(".project-studio-tabs");
                    if (tabs) {
                        tabs.scrollIntoView({
                            behavior: "smooth",
                            block: "start",
                        });
                    }
                });
            });

        const requestedTab = window.location.hash.replace("#", "");
        activateTab(requestedTab || "overview", false);
    }

    document
        .querySelectorAll(".project-studio-progress-line span[data-progress]")
        .forEach(function (bar) {
            const rawValue = Number(bar.dataset.progress || 0);
            const progress = Math.max(0, Math.min(100, rawValue));

            window.requestAnimationFrame(function () {
                bar.style.width = `${progress}%`;
            });
        });
});
