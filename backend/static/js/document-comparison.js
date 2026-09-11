(() => {
    const form = document.querySelector(
        "[data-document-comparison-form]"
    );

    if (!form) {
        return;
    }

    const selectA = form.querySelector(
        "[data-comparison-a]"
    );

    const selectB = form.querySelector(
        "[data-comparison-b]"
    );

    const swapButton = form.querySelector(
        "[data-comparison-swap]"
    );

    const errorBox = form.querySelector(
        "[data-comparison-error]"
    );

    const updateValidation = () => {
        if (!selectA || !selectB) {
            return true;
        }

        const sameDocument = (
            selectA.value
            && selectB.value
            && selectA.value === selectB.value
        );

        if (errorBox) {
            errorBox.hidden = !sameDocument;
        }

        return !sameDocument;
    };

    if (swapButton && selectA && selectB) {
        swapButton.addEventListener(
            "click",
            () => {
                const currentA = selectA.value;
                selectA.value = selectB.value;
                selectB.value = currentA;
                updateValidation();
            }
        );
    }

    if (selectA) {
        selectA.addEventListener(
            "change",
            updateValidation
        );
    }

    if (selectB) {
        selectB.addEventListener(
            "change",
            updateValidation
        );
    }

    form.addEventListener(
        "submit",
        (event) => {
            if (!updateValidation()) {
                event.preventDefault();

                if (selectB) {
                    selectB.focus();
                }
            }
        }
    );

    updateValidation();
})();
