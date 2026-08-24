(function () {
    "use strict";

    const unsafeMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);

    function getToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? (meta.getAttribute("content") || "") : "";
    }

    function protectForm(form) {
        const method = (form.getAttribute("method") || "GET").toUpperCase();
        const token = getToken();

        if (method !== "POST" || !token) {
            return;
        }

        let input = form.querySelector('input[name="csrf_token"]');
        if (!input) {
            input = document.createElement("input");
            input.type = "hidden";
            input.name = "csrf_token";
            form.prepend(input);
        }

        input.value = token;
    }

    function protectAllForms() {
        document.querySelectorAll("form").forEach(protectForm);
    }

    // Explicit hidden fields are included in the templates. These listeners are
    // a second safety layer for forms inserted dynamically by JavaScript.
    protectAllForms();
    document.addEventListener("DOMContentLoaded", protectAllForms);
    document.addEventListener(
        "submit",
        function (event) {
            if (event.target instanceof HTMLFormElement) {
                protectForm(event.target);
            }
        },
        true
    );

    if (typeof window.fetch === "function") {
        const originalFetch = window.fetch.bind(window);

        window.fetch = function (input, init) {
            const options = Object.assign({}, init || {});
            const sourceRequest = input instanceof Request ? input : null;
            const method = (
                options.method ||
                (sourceRequest ? sourceRequest.method : "GET")
            ).toUpperCase();

            const requestUrl = new URL(
                sourceRequest ? sourceRequest.url : String(input),
                window.location.href
            );

            if (
                unsafeMethods.has(method) &&
                requestUrl.origin === window.location.origin
            ) {
                const headers = new Headers(
                    options.headers ||
                    (sourceRequest ? sourceRequest.headers : undefined)
                );
                const token = getToken();

                if (token && !headers.has("X-CSRFToken")) {
                    headers.set("X-CSRFToken", token);
                }

                headers.set("X-Requested-With", "XMLHttpRequest");
                options.headers = headers;
            }

            return originalFetch(input, options);
        };
    }

    window.LifeOSSecurity = Object.freeze({
        get csrfToken() {
            return getToken();
        }
    });
})();
