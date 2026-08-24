(function () {
    "use strict";

    function refreshWorkspace(workspace) {
        const checkboxes = Array.from(
            workspace.querySelectorAll("[data-document-suggestion-checkbox]")
        );

        const selected = checkboxes.filter((checkbox) => checkbox.checked);
        const count = workspace.querySelector(
            "[data-document-suggestion-selected-count]"
        );
        const submit = workspace.querySelector(
            "[data-document-suggestion-bulk-submit]"
        );
        const selectAll = workspace.querySelector(
            "[data-document-suggestion-select-all]"
        );

        if (count) {
            count.textContent = String(selected.length);
        }

        if (submit) {
            submit.disabled = selected.length === 0;
        }

        if (selectAll) {
            selectAll.checked = (
                checkboxes.length > 0
                && selected.length === checkboxes.length
            );
            selectAll.indeterminate = (
                selected.length > 0
                && selected.length < checkboxes.length
            );
        }
    }

    document.querySelectorAll(
        "[data-document-suggestion-workspace]"
    ).forEach((workspace) => {
        workspace.addEventListener("change", (event) => {
            const selectAll = event.target.closest(
                "[data-document-suggestion-select-all]"
            );

            if (selectAll) {
                workspace.querySelectorAll(
                    "[data-document-suggestion-checkbox]"
                ).forEach((checkbox) => {
                    checkbox.checked = selectAll.checked;
                });
            }

            refreshWorkspace(workspace);
        });

        refreshWorkspace(workspace);
    });
})();
