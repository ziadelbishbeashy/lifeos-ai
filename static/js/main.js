document.addEventListener("DOMContentLoaded", function () {
    // Progress bars: read width from data-progress instead of inline style
    document.querySelectorAll(".progress-fill").forEach(function (el) {
        const value = parseInt(el.getAttribute("data-progress"), 10) || 0;
        el.style.width = Math.max(0, Math.min(100, value)) + "%";
    });

    // No Deadline checkbox disables the deadline input
    const noDeadlineCheckbox = document.getElementById("no-deadline-checkbox");
    const deadlineInput = document.getElementById("deadline-input");

    if (noDeadlineCheckbox && deadlineInput) {
        const syncDeadlineState = function () {
            deadlineInput.disabled = noDeadlineCheckbox.checked;
            if (noDeadlineCheckbox.checked) {
                deadlineInput.value = "";
            }
        };

        noDeadlineCheckbox.addEventListener("change", syncDeadlineState);
        syncDeadlineState();
    }

    // Auto-dismiss flash messages after a few seconds
    document.querySelectorAll(".flash").forEach(function (el) {
        setTimeout(function () {
            el.style.transition = "opacity 0.4s ease";
            el.style.opacity = "0";
            setTimeout(function () { el.remove(); }, 400);
        }, 4000);
    });
});
