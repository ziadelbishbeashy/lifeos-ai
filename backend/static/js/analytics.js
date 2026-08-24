(() => {
    const page = document.querySelector("[data-analytics-page]");
    if (!page) return;

    const periodSelect = page.querySelector("[data-period-select]");
    const customDates = page.querySelector("[data-custom-dates]");
    const printButton = page.querySelector("[data-analytics-print]");

    const syncCustomDates = () => {
        if (!periodSelect || !customDates) return;
        customDates.classList.toggle("is-hidden", periodSelect.value !== "custom");
    };

    periodSelect?.addEventListener("change", syncCustomDates);
    syncCustomDates();

    printButton?.addEventListener("click", () => {
        window.print();
    });
})();
