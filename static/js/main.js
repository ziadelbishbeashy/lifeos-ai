document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".progress-fill").forEach(function (element) {
        const value = parseInt(
            element.getAttribute("data-progress"),
            10
        ) || 0;

        element.style.width =
            Math.max(0, Math.min(100, value)) + "%";
    });

    document
        .querySelectorAll(".progress-ring, .mini-progress-ring")
        .forEach(function (element) {
            const value = parseInt(
                element.getAttribute("data-progress"),
                10
            ) || 0;

            element.style.setProperty(
                "--progress",
                Math.max(0, Math.min(100, value))
            );
        });

    function connectNoDeadlineCheckbox(checkboxId, inputId) {
        const checkbox = document.getElementById(checkboxId);
        const input = document.getElementById(inputId);

        if (!checkbox || !input) {
            return;
        }

        function updateDeadlineState() {
            input.disabled = checkbox.checked;

            if (checkbox.checked) {
                input.value = "";
            }
        }

        checkbox.addEventListener("change", updateDeadlineState);
        updateDeadlineState();
    }

    connectNoDeadlineCheckbox(
        "no-deadline-checkbox",
        "deadline-input"
    );

    connectNoDeadlineCheckbox(
        "task-no-deadline-checkbox",
        "task-deadline-input"
    );

    connectNoDeadlineCheckbox(
        "edit-task-no-deadline-checkbox",
        "edit-task-deadline-input"
    );

    const sidebar = document.getElementById("appSidebar");
    const sidebarOverlay = document.getElementById("sidebarOverlay");
    const mobileMenuButton = document.getElementById("mobileMenuButton");
    const sidebarCloseButton = document.getElementById("sidebarCloseButton");

    function openSidebar() {
        document.body.classList.add("sidebar-open");

        if (sidebar) {
            sidebar.setAttribute("aria-hidden", "false");
        }
    }

    function closeSidebar() {
        document.body.classList.remove("sidebar-open");

        if (sidebar) {
            sidebar.setAttribute("aria-hidden", "true");
        }
    }

    if (mobileMenuButton) {
        mobileMenuButton.addEventListener("click", openSidebar);
    }

    if (sidebarCloseButton) {
        sidebarCloseButton.addEventListener("click", closeSidebar);
    }

    if (sidebarOverlay) {
        sidebarOverlay.addEventListener("click", closeSidebar);
    }

    document.querySelectorAll(".app-navigation a").forEach(function (link) {
        link.addEventListener("click", function () {
            if (window.innerWidth <= 980) {
                closeSidebar();
            }
        });
    });

    const profileMenuButton = document.getElementById("profileMenuButton");
    const profileDropdown = document.getElementById("profileDropdown");

    function closeProfileMenu() {
        if (!profileMenuButton || !profileDropdown) {
            return;
        }

        profileDropdown.classList.remove("open");
        profileMenuButton.setAttribute("aria-expanded", "false");
    }

    if (profileMenuButton && profileDropdown) {
        profileMenuButton.addEventListener("click", function (event) {
            event.stopPropagation();

            const isOpen = profileDropdown.classList.toggle("open");

            profileMenuButton.setAttribute(
                "aria-expanded",
                isOpen ? "true" : "false"
            );
        });

        profileDropdown.addEventListener("click", function (event) {
            event.stopPropagation();
        });

        document.addEventListener("click", closeProfileMenu);
    }

    document.querySelectorAll(".flash").forEach(function (element) {
        const closeButton = element.querySelector(".flash-close");

        function dismissFlash() {
            element.classList.add("flash-hiding");

            window.setTimeout(function () {
                element.remove();
            }, 300);
        }

        if (closeButton) {
            closeButton.addEventListener("click", dismissFlash);
        }

        window.setTimeout(dismissFlash, 5000);
    });

    const dashboardGreeting = document.getElementById("dashboardGreeting");

    if (dashboardGreeting) {
        const hour = new Date().getHours();
        let greeting = "Welcome back";

        if (hour < 12) {
            greeting = "Good morning";
        } else if (hour < 18) {
            greeting = "Good afternoon";
        } else {
            greeting = "Good evening";
        }

        const existingName = dashboardGreeting.textContent
            .split(",")
            .slice(1)
            .join(",")
            .trim();

        dashboardGreeting.textContent = existingName
            ? greeting + ", " + existingName
            : greeting;
    }

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
            closeSidebar();
            closeProfileMenu();
        }
    });
});
(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {

        /* =========================================
           Progress Bars
           ========================================= */

        function clampProgress(value) {
            const numericValue = Number(value) || 0;

            return Math.max(
                0,
                Math.min(100, numericValue)
            );
        }

        document
            .querySelectorAll("[data-progress]")
            .forEach(function (progressBar) {
                const progress = clampProgress(
                    progressBar.dataset.progress
                );

                progressBar.style.width =
                    progress + "%";
            });


        /* =========================================
           Project Modal
           ========================================= */

        const modalOverlay =
            document.getElementById(
                "projectModalOverlay"
            );

        const modalOpenButtons =
            document.querySelectorAll(
                "[data-open-project-modal]"
            );

        const modalCloseButtons =
            document.querySelectorAll(
                "[data-close-project-modal]"
            );

        function openProjectModal() {
            if (!modalOverlay) {
                return;
            }

            modalOverlay.classList.add("open");

            modalOverlay.setAttribute(
                "aria-hidden",
                "false"
            );

            document.body.classList.add(
                "project-modal-open"
            );

            const titleInput =
                document.getElementById(
                    "projectTitle"
                );

            setTimeout(function () {
                if (titleInput) {
                    titleInput.focus();
                }
            }, 100);
        }

        function closeProjectModal() {
            if (!modalOverlay) {
                return;
            }

            modalOverlay.classList.remove("open");

            modalOverlay.setAttribute(
                "aria-hidden",
                "true"
            );

            document.body.classList.remove(
                "project-modal-open"
            );

            if (
                window.location.hash ===
                "#new-project"
            ) {
                history.replaceState(
                    null,
                    "",
                    window.location.pathname
                );
            }
        }

        modalOpenButtons.forEach(
            function (button) {
                button.addEventListener(
                    "click",
                    openProjectModal
                );
            }
        );

        modalCloseButtons.forEach(
            function (button) {
                button.addEventListener(
                    "click",
                    closeProjectModal
                );
            }
        );

        if (modalOverlay) {
            modalOverlay.addEventListener(
                "click",
                function (event) {
                    if (event.target === modalOverlay) {
                        closeProjectModal();
                    }
                }
            );
        }

        document.addEventListener(
            "keydown",
            function (event) {
                if (
                    event.key === "Escape"
                    && modalOverlay
                    && modalOverlay.classList.contains(
                        "open"
                    )
                ) {
                    closeProjectModal();
                }
            }
        );

        if (
            window.location.hash ===
            "#new-project"
        ) {
            openProjectModal();
        }


        /* =========================================
           Project Filtering
           ========================================= */

        const searchInput =
            document.getElementById(
                "projectSearchInput"
            );

        const statusFilter =
            document.getElementById(
                "projectStatusFilter"
            );

        const priorityFilter =
            document.getElementById(
                "projectPriorityFilter"
            );

        const projectCards =
            Array.from(
                document.querySelectorAll(
                    "[data-project-card]"
                )
            );

        const statusTabs =
            document.querySelectorAll(
                "[data-project-tab]"
            );

        const visibleProjectCount =
            document.getElementById(
                "visibleProjectCount"
            );

        const noResults =
            document.getElementById(
                "projectNoResults"
            );

        const projectsGrid =
            document.getElementById(
                "projectsGrid"
            );

        let selectedTab = "all";

        function projectMatchesSearch(
            projectCard,
            searchValue
        ) {
            if (!searchValue) {
                return true;
            }

            const searchableContent = [
                projectCard.dataset.title,
                projectCard.dataset.description,
                projectCard.dataset.type,
                projectCard.dataset.stack,
                projectCard.dataset.phase
            ]
                .join(" ")
                .toLowerCase();

            return searchableContent.includes(
                searchValue
            );
        }

        function applyProjectFilters() {
            if (!projectCards.length) {
                return;
            }

            const searchValue =
                searchInput
                    ? searchInput.value
                        .trim()
                        .toLowerCase()
                    : "";

            const statusValue =
                statusFilter
                    ? statusFilter.value
                    : "all";

            const priorityValue =
                priorityFilter
                    ? priorityFilter.value
                    : "all";

            let visibleCount = 0;

            projectCards.forEach(
                function (projectCard) {
                    const matchesSearch =
                        projectMatchesSearch(
                            projectCard,
                            searchValue
                        );

                    const matchesSelectStatus =
                        statusValue === "all"
                        || projectCard.dataset.status
                            === statusValue;

                    const matchesPriority =
                        priorityValue === "all"
                        || projectCard.dataset.priority
                            === priorityValue;

                    const matchesTab =
                        selectedTab === "all"
                        || projectCard.dataset.status
                            === selectedTab;

                    const isVisible =
                        matchesSearch
                        && matchesSelectStatus
                        && matchesPriority
                        && matchesTab;

                    projectCard.hidden = !isVisible;

                    if (isVisible) {
                        visibleCount += 1;
                    }
                }
            );

            if (visibleProjectCount) {
                visibleProjectCount.textContent =
                    visibleCount;
            }

            if (noResults) {
                noResults.hidden =
                    visibleCount !== 0;
            }

            if (projectsGrid) {
                projectsGrid.hidden =
                    visibleCount === 0;
            }
        }

        if (searchInput) {
            searchInput.addEventListener(
                "input",
                applyProjectFilters
            );
        }

        if (statusFilter) {
            statusFilter.addEventListener(
                "change",
                applyProjectFilters
            );
        }

        if (priorityFilter) {
            priorityFilter.addEventListener(
                "change",
                applyProjectFilters
            );
        }

        statusTabs.forEach(
            function (tabButton) {
                tabButton.addEventListener(
                    "click",
                    function () {
                        selectedTab =
                            tabButton.dataset.projectTab;

                        statusTabs.forEach(
                            function (otherTab) {
                                otherTab.classList.remove(
                                    "active"
                                );
                            }
                        );

                        tabButton.classList.add(
                            "active"
                        );

                        applyProjectFilters();
                    }
                );
            }
        );


        /* =========================================
           Clear Project Filters
           ========================================= */

        const clearFilterButtons = [
            document.getElementById(
                "clearProjectFilters"
            ),
            document.getElementById(
                "clearProjectFiltersEmpty"
            )
        ].filter(Boolean);

        function clearProjectFilters() {
            if (searchInput) {
                searchInput.value = "";
            }

            if (statusFilter) {
                statusFilter.value = "all";
            }

            if (priorityFilter) {
                priorityFilter.value = "all";
            }

            selectedTab = "all";

            statusTabs.forEach(
                function (tabButton) {
                    tabButton.classList.toggle(
                        "active",
                        tabButton.dataset.projectTab
                            === "all"
                    );
                }
            );

            applyProjectFilters();
        }

        clearFilterButtons.forEach(
            function (button) {
                button.addEventListener(
                    "click",
                    clearProjectFilters
                );
            }
        );


        /* =========================================
           Deadline Controls
           ========================================= */

        document
            .querySelectorAll("[data-no-deadline]")
            .forEach(function (checkbox) {
                const targetId =
                    checkbox.dataset.deadlineTarget;

                const deadlineInput =
                    document.getElementById(
                        targetId
                    );

                if (!deadlineInput) {
                    return;
                }

                function updateDeadlineInput() {
                    deadlineInput.disabled =
                        checkbox.checked;

                    if (checkbox.checked) {
                        deadlineInput.value = "";
                    }
                }

                checkbox.addEventListener(
                    "change",
                    updateDeadlineInput
                );

                updateDeadlineInput();
            });


        /* =========================================
           Edit Progress Preview
           ========================================= */

        const progressInput =
            document.querySelector(
                "[data-progress-input]"
            );

        const progressPreview =
            document.querySelector(
                "[data-progress-preview]"
            );

        const progressLabel =
            document.querySelector(
                "[data-progress-label]"
            );

        if (progressInput) {
            progressInput.addEventListener(
                "input",
                function () {
                    const progress = clampProgress(
                        progressInput.value
                    );

                    if (progressPreview) {
                        progressPreview.style.width =
                            progress + "%";
                    }

                    if (progressLabel) {
                        progressLabel.textContent =
                            progress + "%";
                    }
                }
            );
        }


        /* =========================================
           Confirmation Forms
           ========================================= */

        document
            .querySelectorAll(
                "[data-confirm-form]"
            )
            .forEach(function (form) {
                form.addEventListener(
                    "submit",
                    function (event) {
                        const message =
                            form.dataset.confirmForm
                            || "Are you sure?";

                        if (!window.confirm(message)) {
                            event.preventDefault();
                        }
                    }
                );
            });

    });
})();
/* =========================================================
   PHASE 4 — LIGHT / DARK THEME
   ========================================================= */

document.addEventListener("DOMContentLoaded", function () {
    const themeButton = document.getElementById("themeToggleButton");
    const themeLabel = document.getElementById("themeToggleLabel");

    if (!themeButton) {
        return;
    }

    const storageKey = "lifeos-theme";

    function getTheme() {
        return (
            document.documentElement.getAttribute("data-theme") ||
            "dark"
        );
    }

    function updateThemeInterface(theme) {
        const isLight = theme === "light";

        themeButton.setAttribute(
            "aria-pressed",
            isLight ? "true" : "false"
        );

        themeButton.setAttribute(
            "aria-label",
            isLight
                ? "Switch to dark mode"
                : "Switch to light mode"
        );

        themeButton.setAttribute(
            "title",
            isLight
                ? "Switch to dark mode"
                : "Switch to light mode"
        );

        if (themeLabel) {
            themeLabel.textContent = isLight
                ? "Light mode"
                : "Dark mode";
        }
    }

    function setTheme(theme) {
        const validTheme =
            theme === "light" ? "light" : "dark";

        document.documentElement.setAttribute(
            "data-theme",
            validTheme
        );

        localStorage.setItem(
            storageKey,
            validTheme
        );

        updateThemeInterface(validTheme);
    }

    updateThemeInterface(getTheme());

    themeButton.addEventListener("click", function () {
        const currentTheme = getTheme();

        setTheme(
            currentTheme === "dark"
                ? "light"
                : "dark"
        );
    });
});

/* =========================================================
   PHASE 4.2 — ADVANCED IN-APP NOTIFICATION CENTER
   ========================================================= */

document.addEventListener("DOMContentLoaded", function () {
    "use strict";

    const notificationWrapper = document.getElementById("notificationCenterWrapper");
    const notificationButton = document.getElementById("notificationButton");
    const notificationPanel = document.getElementById("notificationPanel");
    const notificationPanelClose = document.getElementById("notificationPanelClose");
    const notificationBadge = document.getElementById("notificationBadge");
    const notificationList = document.getElementById("notificationList");
    const notificationEmptyState = document.getElementById("notificationEmptyState");
    const notificationSummary = document.getElementById("notificationSummary");
    const allNotificationCount = document.getElementById("allNotificationCount");
    const unreadNotificationCount = document.getElementById("unreadNotificationCount");
    const markAllReadButton = document.getElementById("markAllNotificationsRead");
    const clearReadButton = document.getElementById("clearReadNotifications");

    const notificationFilterButtons = document.querySelectorAll(
        "[data-notification-filter]"
    );

    const profileMenuButton = document.getElementById("profileMenuButton");

    if (
        !notificationWrapper ||
        !notificationButton ||
        !notificationPanel ||
        !notificationList
    ) {
        console.warn("Notification center elements were not found.");
        return;
    }

    /* ---------------- Storage ---------------- */

    const notificationUser =
        document.body.dataset.notificationUser || "guest";

    const storageKey = `lifeos-notifications-${notificationUser}`;
    const maximumNotifications = 50;

    let currentFilter = "all";
    let notifications = loadNotifications();

    function loadNotifications() {
        try {
            const storedValue = localStorage.getItem(storageKey);

            if (!storedValue) {
                return [];
            }

            const parsedValue = JSON.parse(storedValue);

            return Array.isArray(parsedValue) ? parsedValue : [];
        } catch (error) {
            console.warn("LifeOS notifications could not be loaded.", error);
            return [];
        }
    }

    function saveNotifications() {
        try {
            localStorage.setItem(storageKey, JSON.stringify(notifications));
        } catch (error) {
            console.warn("LifeOS notifications could not be saved.", error);
        }
    }

    function createNotificationId() {
        if (
            window.crypto &&
            typeof window.crypto.randomUUID === "function"
        ) {
            return window.crypto.randomUUID();
        }

        return (
            Date.now().toString(36) +
            Math.random().toString(36).slice(2)
        );
    }

    /* ---------------- Helpers ---------------- */

    function normalizeNotificationType(type) {
        const normalized = String(type || "info")
            .trim()
            .toLowerCase();

        if (normalized === "danger" || normalized === "error") {
            return "error";
        }

        const supportedTypes = [
            "success",
            "warning",
            "deadline",
            "overdue",
            "system"
        ];

        return supportedTypes.includes(normalized)
            ? normalized
            : "info";
    }

    function getDefaultTitle(type) {
        const titles = {
            success: "Action completed",
            error: "Something needs attention",
            warning: "Important update",
            info: "Workspace update",
            deadline: "Deadline approaching",
            overdue: "Task overdue",
            system: "LifeOS notification"
        };

        return titles[type] || titles.info;
    }

    function getNotificationSymbol(type) {
        const symbols = {
            success: "✓",
            error: "!",
            warning: "!",
            info: "i",
            deadline: "⏱",
            overdue: "!",
            system: "L"
        };

        return symbols[type] || symbols.info;
    }

    function formatRelativeTime(timestamp) {
        const createdDate = new Date(timestamp);

        if (Number.isNaN(createdDate.getTime())) {
            return "Recently";
        }

        const difference = Date.now() - createdDate.getTime();
        const seconds = Math.floor(difference / 1000);

        if (seconds < 30) {
            return "Just now";
        }

        const minutes = Math.floor(seconds / 60);

        if (minutes < 60) {
            return `${minutes} ${minutes === 1 ? "minute" : "minutes"} ago`;
        }

        const hours = Math.floor(minutes / 60);

        if (hours < 24) {
            return `${hours} ${hours === 1 ? "hour" : "hours"} ago`;
        }

        const days = Math.floor(hours / 24);

        if (days < 7) {
            return `${days} ${days === 1 ? "day" : "days"} ago`;
        }

        return createdDate.toLocaleDateString(undefined, {
            month: "short",
            day: "numeric",
            year:
                createdDate.getFullYear() !== new Date().getFullYear()
                    ? "numeric"
                    : undefined
        });
    }

    function addNotification(data = {}) {
        const type = normalizeNotificationType(data.type);

        const notification = {
            id: data.id || createNotificationId(),
            type,
            title: String(
                data.title || getDefaultTitle(type)
            ).trim(),
            message: String(data.message || "").trim(),
            url: data.url ? String(data.url) : "",
            isRead: Boolean(data.isRead),
            createdAt: data.createdAt || new Date().toISOString()
        };

        if (!notification.message) {
            return null;
        }

        notifications.unshift(notification);
        notifications = notifications.slice(0, maximumNotifications);

        saveNotifications();
        renderNotifications();

        return notification;
    }

    /* ---------------- Flask flash messages ---------------- */

    function getFlashType(flashElement) {
        if (flashElement.classList.contains("flash-success")) {
            return "success";
        }

        if (
            flashElement.classList.contains("flash-error") ||
            flashElement.classList.contains("flash-danger")
        ) {
            return "error";
        }

        if (flashElement.classList.contains("flash-warning")) {
            return "warning";
        }

        return "info";
    }

    function captureFlashNotifications() {
        const flashMessages = document.querySelectorAll(".flash");

        flashMessages.forEach(function (flashElement) {
            if (
                flashElement.dataset.notificationCaptured === "true"
            ) {
                return;
            }

            const messageElement = flashElement.querySelector("span");

            const message = messageElement
                ? messageElement.textContent.trim()
                : flashElement.textContent.trim();

            if (!message) {
                return;
            }

            flashElement.dataset.notificationCaptured = "true";

            const type = getFlashType(flashElement);

            const recentDuplicate = notifications.some(
                function (notification) {
                    const createdAt = new Date(
                        notification.createdAt
                    ).getTime();

                    return (
                        notification.message === message &&
                        Date.now() - createdAt < 15000
                    );
                }
            );

            if (recentDuplicate) {
                return;
            }

            addNotification({
                type,
                title: getDefaultTitle(type),
                message
            });
        });
    }

    /* ---------------- Notification items ---------------- */

    function createNotificationElement(notification) {
        const item = document.createElement("button");

        item.type = "button";
        item.className =
            `notification-item notification-type-${notification.type}`;

        if (!notification.isRead) {
            item.classList.add("notification-unread");
        }

        item.dataset.notificationId = notification.id;

        const icon = document.createElement("span");
        icon.className = "notification-item-icon";
        icon.textContent = getNotificationSymbol(notification.type);

        const content = document.createElement("span");
        content.className = "notification-item-content";

        const topLine = document.createElement("span");
        topLine.className = "notification-item-topline";

        const title = document.createElement("strong");
        title.textContent = notification.title;

        topLine.appendChild(title);

        if (!notification.isRead) {
            const unreadDot = document.createElement("i");

            unreadDot.className = "notification-unread-dot";
            unreadDot.setAttribute("aria-hidden", "true");

            topLine.appendChild(unreadDot);
        }

        const message = document.createElement("span");
        message.className = "notification-item-message";
        message.textContent = notification.message;

        const meta = document.createElement("span");
        meta.className = "notification-item-meta";
        meta.textContent = formatRelativeTime(notification.createdAt);

        content.appendChild(topLine);
        content.appendChild(message);
        content.appendChild(meta);

        item.appendChild(icon);
        item.appendChild(content);

        item.addEventListener("click", function () {
            markNotificationRead(notification.id);

            if (notification.url) {
                window.location.href = notification.url;
            }
        });

        return item;
    }

    function renderNotifications() {
        notificationList.innerHTML = "";

        const unreadCount = notifications.filter(
            notification => !notification.isRead
        ).length;

        const filteredNotifications = notifications.filter(
            function (notification) {
                if (currentFilter === "unread") {
                    return !notification.isRead;
                }

                return true;
            }
        );

        if (notificationBadge) {
            notificationBadge.textContent =
                unreadCount > 99 ? "99+" : String(unreadCount);

            notificationBadge.hidden = unreadCount === 0;
        }

        if (allNotificationCount) {
            allNotificationCount.textContent =
                String(notifications.length);
        }

        if (unreadNotificationCount) {
            unreadNotificationCount.textContent =
                String(unreadCount);
        }

        if (notificationSummary) {
            notificationSummary.textContent =
                unreadCount === 0
                    ? "You are all caught up"
                    : `${unreadCount} unread ${
                        unreadCount === 1
                            ? "notification"
                            : "notifications"
                    }`;
        }

        if (markAllReadButton) {
            markAllReadButton.disabled = unreadCount === 0;
        }

        const readCount = notifications.filter(
            notification => notification.isRead
        ).length;

        if (clearReadButton) {
            clearReadButton.disabled = readCount === 0;
        }

        if (notificationEmptyState) {
            notificationEmptyState.hidden =
                filteredNotifications.length > 0;
        }

        filteredNotifications.forEach(function (notification) {
            notificationList.appendChild(
                createNotificationElement(notification)
            );
        });
    }

    /* ---------------- Notification actions ---------------- */

    function markNotificationRead(notificationId) {
        let changed = false;

        notifications = notifications.map(function (notification) {
            if (
                notification.id === notificationId &&
                !notification.isRead
            ) {
                changed = true;

                return {
                    ...notification,
                    isRead: true
                };
            }

            return notification;
        });

        if (changed) {
            saveNotifications();
            renderNotifications();
        }
    }

    function markAllNotificationsRead() {
        notifications = notifications.map(function (notification) {
            return {
                ...notification,
                isRead: true
            };
        });

        saveNotifications();
        renderNotifications();
    }

    function clearReadNotifications() {
        notifications = notifications.filter(
            notification => !notification.isRead
        );

        saveNotifications();
        renderNotifications();
    }

    /* ---------------- Open and close panel ---------------- */

    function openNotificationPanel() {
        notificationPanel.classList.add("open");
        notificationPanel.setAttribute("aria-hidden", "false");

        notificationButton.setAttribute("aria-expanded", "true");
        notificationButton.classList.add("active");

        const profileDropdown =
            document.getElementById("profileDropdown");

        if (profileDropdown) {
            profileDropdown.classList.remove("open");
        }

        if (profileMenuButton) {
            profileMenuButton.setAttribute(
                "aria-expanded",
                "false"
            );
        }
    }

    function closeNotificationPanel() {
        notificationPanel.classList.remove("open");
        notificationPanel.setAttribute("aria-hidden", "true");

        notificationButton.setAttribute("aria-expanded", "false");
        notificationButton.classList.remove("active");
    }

    function toggleNotificationPanel() {
        if (notificationPanel.classList.contains("open")) {
            closeNotificationPanel();
        } else {
            openNotificationPanel();
        }
    }

    notificationButton.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();

        toggleNotificationPanel();
    });

    notificationPanel.addEventListener("click", function (event) {
        event.stopPropagation();
    });

    if (notificationPanelClose) {
        notificationPanelClose.addEventListener(
            "click",
            closeNotificationPanel
        );
    }

    document.addEventListener("click", closeNotificationPanel);

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
            closeNotificationPanel();
        }
    });

    if (profileMenuButton) {
        profileMenuButton.addEventListener(
            "click",
            closeNotificationPanel
        );
    }

    /* ---------------- Filters ---------------- */

    notificationFilterButtons.forEach(function (filterButton) {
        filterButton.addEventListener("click", function () {
            currentFilter =
                filterButton.dataset.notificationFilter || "all";

            notificationFilterButtons.forEach(
                function (otherButton) {
                    const isActive = otherButton === filterButton;

                    otherButton.classList.toggle(
                        "active",
                        isActive
                    );

                    otherButton.setAttribute(
                        "aria-selected",
                        isActive ? "true" : "false"
                    );
                }
            );

            renderNotifications();
        });
    });

    if (markAllReadButton) {
        markAllReadButton.addEventListener(
            "click",
            markAllNotificationsRead
        );
    }

    if (clearReadButton) {
        clearReadButton.addEventListener(
            "click",
            clearReadNotifications
        );
    }

    /* ---------------- Public notification function ---------------- */

    window.lifeOSPushNotification = function (notificationData) {
        return addNotification(notificationData || {});
    };

    captureFlashNotifications();
    renderNotifications();

    window.setInterval(renderNotifications, 60000);
});

/* =========================================================
   PHASE 4.3 — CUSTOM CONFIRMATION MODALS
   ========================================================= */

document.addEventListener("DOMContentLoaded", function () {
    "use strict";

    const backdrop =
        document.getElementById("confirmationModalBackdrop");

    const modal =
        document.getElementById("confirmationModal");

    const icon =
        document.getElementById("confirmationModalIcon");

    const title =
        document.getElementById("confirmationModalTitle");

    const message =
        document.getElementById("confirmationModalMessage");

    const cancelButton =
        document.getElementById("confirmationCancelButton");

    const confirmButton =
        document.getElementById("confirmationConfirmButton");

    if (
        !backdrop ||
        !modal ||
        !title ||
        !message ||
        !cancelButton ||
        !confirmButton
    ) {
        console.warn(
            "LifeOS confirmation modal elements are missing."
        );

        return;
    }

    let pendingAction = null;
    let lastFocusedElement = null;


    function getConfirmationConfig(element) {
        return {
            title:
                element.dataset.confirmTitle ||
                "Are you sure?",

            message:
                element.dataset.confirmMessage ||
                "This action needs your confirmation before continuing.",

            confirmText:
                element.dataset.confirmText ||
                "Confirm",

            cancelText:
                element.dataset.confirmCancel ||
                "Cancel",

            variant:
                element.dataset.confirmVariant ||
                "default",

            icon:
                element.dataset.confirmIcon ||
                "!"
        };
    }


    function openConfirmationModal(config, onConfirm) {
        pendingAction = onConfirm;
        lastFocusedElement = document.activeElement;

        title.textContent = config.title;
        message.textContent = config.message;
        confirmButton.textContent = config.confirmText;
        cancelButton.textContent = config.cancelText;

        if (icon) {
            icon.textContent = config.icon;
        }

        modal.classList.remove(
            "danger",
            "success",
            "warning"
        );

        if (config.variant !== "default") {
            modal.classList.add(config.variant);
        }

        backdrop.hidden = false;

        document.body.classList.add(
            "confirmation-modal-lock"
        );

        setTimeout(function () {
            cancelButton.focus();
        }, 50);
    }


    function closeConfirmationModal() {
        backdrop.hidden = true;

        document.body.classList.remove(
            "confirmation-modal-lock"
        );

        pendingAction = null;

        if (
            lastFocusedElement &&
            typeof lastFocusedElement.focus === "function"
        ) {
            lastFocusedElement.focus();
        }

        lastFocusedElement = null;
    }


    function approveConfirmation() {
        const action = pendingAction;

        closeConfirmationModal();

        if (typeof action === "function") {
            action();
        }
    }


    document.addEventListener(
        "submit",
        function (event) {
            const form =
                event.target.closest("form[data-confirm]");

            if (!form) {
                return;
            }

            if (form.dataset.confirmApproved === "true") {
                delete form.dataset.confirmApproved;
                return;
            }

            event.preventDefault();

            const submitter =
                event.submitter || null;

            const config =
                getConfirmationConfig(form);

            openConfirmationModal(
                config,
                function () {
                    form.dataset.confirmApproved = "true";

                    if (
                        submitter &&
                        typeof form.requestSubmit === "function"
                    ) {
                        form.requestSubmit(submitter);
                    } else if (
                        typeof form.requestSubmit === "function"
                    ) {
                        form.requestSubmit();
                    } else {
                        form.submit();
                    }
                }
            );
        }
    );


    document.addEventListener(
        "click",
        function (event) {
            const trigger =
                event.target.closest(
                    "a[data-confirm], button[data-confirm]:not([type='submit'])"
                );

            if (!trigger) {
                return;
            }

            event.preventDefault();

            const config =
                getConfirmationConfig(trigger);

            openConfirmationModal(
                config,
                function () {
                    if (
                        trigger.tagName.toLowerCase() ===
                        "a"
                    ) {
                        window.location.href =
                            trigger.href;
                        return;
                    }

                    trigger.dispatchEvent(
                        new CustomEvent(
                            "lifeos:confirmed-action",
                            {
                                bubbles: true,
                                detail: {
                                    source: trigger
                                }
                            }
                        )
                    );
                }
            );
        }
    );


    cancelButton.addEventListener(
        "click",
        closeConfirmationModal
    );


    confirmButton.addEventListener(
        "click",
        approveConfirmation
    );


    backdrop.addEventListener(
        "click",
        function (event) {
            if (event.target === backdrop) {
                closeConfirmationModal();
            }
        }
    );


    document.addEventListener(
        "keydown",
        function (event) {
            if (backdrop.hidden) {
                return;
            }

            if (event.key === "Escape") {
                closeConfirmationModal();
            }

            if (event.key === "Enter") {
                approveConfirmation();
            }
        }
    );


    window.lifeOSConfirm = function (options, callback) {
        openConfirmationModal(
            {
                title:
                    options.title || "Are you sure?",

                message:
                    options.message ||
                    "This action needs your confirmation before continuing.",

                confirmText:
                    options.confirmText || "Confirm",

                cancelText:
                    options.cancelText || "Cancel",

                variant:
                    options.variant || "default",

                icon:
                    options.icon || "!"
            },
            callback
        );
    };
});

/* =========================================================
   PHASE 4.4 — LOADING STATES AND ANIMATIONS
   FIXED VERSION: works with confirmation modals
   ========================================================= */

document.addEventListener("DOMContentLoaded", function () {
    "use strict";

    const loadingOverlay =
        document.getElementById("globalLoadingOverlay");

    const loadingTitle =
        document.getElementById("globalLoadingTitle");

    const loadingMessage =
        document.getElementById("globalLoadingMessage");

    let loadingTimeout = null;


    function showGlobalLoading(options) {
        if (!loadingOverlay) {
            return;
        }

        const config = options || {};

        if (loadingTitle) {
            loadingTitle.textContent =
                config.title || "Preparing workspace";
        }

        if (loadingMessage) {
            loadingMessage.textContent =
                config.message ||
                "LifeOS AI is processing your request...";
        }

        clearTimeout(loadingTimeout);

        loadingTimeout = setTimeout(function () {
            loadingOverlay.classList.add("active");
            loadingOverlay.setAttribute("aria-hidden", "false");
        }, config.delay || 180);
    }


    function hideGlobalLoading() {
        if (!loadingOverlay) {
            return;
        }

        clearTimeout(loadingTimeout);

        loadingOverlay.classList.remove("active");
        loadingOverlay.setAttribute("aria-hidden", "true");
    }


    function setButtonLoading(button) {
        if (!button) {
            return;
        }

        button.classList.add("is-loading");
        button.disabled = true;
        button.setAttribute("aria-busy", "true");
    }


    function getLoadingConfigFromForm(form) {
        return {
            title:
                form.dataset.loadingTitle ||
                "Saving changes",

            message:
                form.dataset.loadingMessage ||
                "Please wait while LifeOS updates your workspace.",

            delay:
                Number(form.dataset.loadingDelay) || 180
        };
    }


    document.addEventListener("submit", function (event) {
        const form = event.target;

        if (!form || form.tagName.toLowerCase() !== "form") {
            return;
        }

        if (form.dataset.skipLoading === "true") {
            return;
        }

        /*
           Important:
           If another feature already prevented the submit,
           do not show loading.

           This fixes the conflict with Phase 4.3 confirmation modal.
        */
        if (event.defaultPrevented) {
            return;
        }

        /*
           If the form needs confirmation, loading should start only
           after the confirmation modal approves the submit.
        */
        if (
            form.hasAttribute("data-confirm") &&
            form.dataset.confirmApproved !== "true"
        ) {
            return;
        }

        if (form.dataset.loadingStarted === "true") {
            event.preventDefault();
            return;
        }

        form.dataset.loadingStarted = "true";

        const submitButton =
            event.submitter ||
            form.querySelector(
                "button[type='submit'], input[type='submit']"
            );

        setButtonLoading(submitButton);

        showGlobalLoading(
            getLoadingConfigFromForm(form)
        );
    });


    document.addEventListener("click", function (event) {
        const link =
            event.target.closest("a[data-page-loading]");

        if (!link) {
            return;
        }

        if (
            link.target === "_blank" ||
            link.hasAttribute("download") ||
            link.href.startsWith("mailto:") ||
            link.href.startsWith("tel:") ||
            link.getAttribute("href").startsWith("#")
        ) {
            return;
        }

        showGlobalLoading({
            title:
                link.dataset.loadingTitle ||
                "Opening page",

            message:
                link.dataset.loadingMessage ||
                "Loading your LifeOS workspace..."
        });
    });


    window.lifeOSLoading = {
        show: showGlobalLoading,
        hide: hideGlobalLoading,
        button: setButtonLoading
    };


    window.addEventListener("pageshow", function () {
        hideGlobalLoading();

        document
            .querySelectorAll(".is-loading")
            .forEach(function (element) {
                element.classList.remove("is-loading");
                element.disabled = false;
                element.removeAttribute("aria-busy");
            });

        document
            .querySelectorAll("form[data-loading-started]")
            .forEach(function (form) {
                delete form.dataset.loadingStarted;
            });
    });
});

/* =========================================================
   PHASE 5.0 — GENERAL / PROJECT TASK LOGIC UI
   ========================================================= */

document.addEventListener("DOMContentLoaded", function () {
    "use strict";

    function updateTaskScopeFields(scopeRoot) {
        const checkedScope = scopeRoot.querySelector(
            "input[name='task_scope']:checked"
        );

        const projectField = scopeRoot.querySelector(
            "[data-task-project-field]"
        );

        if (!projectField || !checkedScope) {
            return;
        }

        const projectSelect = projectField.querySelector("select");
        const isProjectTask = checkedScope.value === "project";

        projectField.hidden = !isProjectTask;
        projectField.classList.toggle("is-visible", isProjectTask);

        if (projectSelect) {
            projectSelect.required = isProjectTask;

            if (!isProjectTask) {
                projectSelect.value = "";
            }
        }
    }

    document
        .querySelectorAll("form.professional-task-form")
        .forEach(function (form) {
            if (!form.querySelector("[data-task-scope-control]")) {
                return;
            }

            form
                .querySelectorAll("[data-task-scope-control]")
                .forEach(function (radio) {
                    radio.addEventListener("change", function () {
                        updateTaskScopeFields(form);
                    });
                });

            updateTaskScopeFields(form);
        });

    const taskCards = Array.from(
        document.querySelectorAll("[data-task-card]")
    );

    const taskSearchInput = document.getElementById("taskSearchInput");
    const taskStatusFilter = document.getElementById("taskStatusFilter");
    const taskImportanceFilter = document.getElementById("taskImportanceFilter");
    const taskScopeFilter = document.getElementById("taskScopeFilter");
    const taskProjectFilter = document.getElementById("taskProjectFilter");
    const taskNoResults = document.getElementById("taskNoResults");
    const taskList = document.getElementById("professionalTaskList");

    function taskMatchesSearch(taskCard, searchValue) {
        if (!searchValue) {
            return true;
        }

        const searchableContent = [
            taskCard.dataset.title,
            taskCard.dataset.description,
            taskCard.dataset.module,
            taskCard.textContent
        ]
            .join(" ")
            .toLowerCase();

        return searchableContent.includes(searchValue);
    }

    function applyTaskFilters() {
        if (!taskCards.length) {
            return;
        }

        const searchValue = taskSearchInput
            ? taskSearchInput.value.trim().toLowerCase()
            : "";

        const statusValue = taskStatusFilter
            ? taskStatusFilter.value
            : "all";

        const importanceValue = taskImportanceFilter
            ? taskImportanceFilter.value
            : "all";

        const scopeValue = taskScopeFilter
            ? taskScopeFilter.value
            : "all";

        const projectValue = taskProjectFilter
            ? taskProjectFilter.value
            : "all";

        let visibleCount = 0;

        taskCards.forEach(function (taskCard) {
            const matchesSearch = taskMatchesSearch(
                taskCard,
                searchValue
            );

            const matchesStatus =
                statusValue === "all" ||
                (statusValue === "recurring"
                    ? taskCard.dataset.recurring === "true"
                    : taskCard.dataset.status === statusValue);

            const matchesImportance =
                importanceValue === "all" ||
                taskCard.dataset.importance === importanceValue;

            const matchesScope =
                scopeValue === "all" ||
                taskCard.dataset.scope === scopeValue;

            const matchesProject =
                projectValue === "all" ||
                taskCard.dataset.project === projectValue;

            const isVisible =
                matchesSearch &&
                matchesStatus &&
                matchesImportance &&
                matchesScope &&
                matchesProject;

            taskCard.hidden = !isVisible;

            if (isVisible) {
                visibleCount += 1;
            }
        });

        if (taskNoResults) {
            taskNoResults.hidden = visibleCount !== 0;
        }

        if (taskList) {
            taskList.hidden = visibleCount === 0;
        }
    }

    [
        taskSearchInput,
        taskStatusFilter,
        taskImportanceFilter,
        taskScopeFilter,
        taskProjectFilter
    ]
        .filter(Boolean)
        .forEach(function (control) {
            control.addEventListener(
                control.tagName.toLowerCase() === "input"
                    ? "input"
                    : "change",
                applyTaskFilters
            );
        });

    function clearTaskFilters() {
        if (taskSearchInput) taskSearchInput.value = "";
        if (taskStatusFilter) taskStatusFilter.value = "all";
        if (taskImportanceFilter) taskImportanceFilter.value = "all";
        if (taskScopeFilter) taskScopeFilter.value = "all";
        if (taskProjectFilter) taskProjectFilter.value = "all";
        applyTaskFilters();
    }

    [
        document.getElementById("clearTaskFilters"),
        document.getElementById("clearTaskFiltersEmpty")
    ]
        .filter(Boolean)
        .forEach(function (button) {
            button.addEventListener("click", clearTaskFilters);
        });

    applyTaskFilters();
});

/* =========================================================
   PHASE 5.0 — TASK MODAL OPEN/CLOSE SUPPORT
   ========================================================= */

document.addEventListener("DOMContentLoaded", function () {
    "use strict";

    const taskModalOverlay = document.getElementById("taskModalOverlay");

    if (!taskModalOverlay) {
        return;
    }

    const openTaskButtons = document.querySelectorAll("[data-open-task-modal]");
    const closeTaskButtons = document.querySelectorAll("[data-close-task-modal]");

    function openTaskModal() {
        taskModalOverlay.classList.add("open");
        taskModalOverlay.setAttribute("aria-hidden", "false");
        document.body.classList.add("project-modal-open");

        const firstInput = taskModalOverlay.querySelector(
            "input[name='title'], input, select, textarea"
        );

        window.setTimeout(function () {
            if (firstInput) {
                firstInput.focus();
            }
        }, 100);
    }

    function closeTaskModal() {
        taskModalOverlay.classList.remove("open");
        taskModalOverlay.setAttribute("aria-hidden", "true");
        document.body.classList.remove("project-modal-open");
    }

    openTaskButtons.forEach(function (button) {
        button.addEventListener("click", function (event) {
            event.preventDefault();
            openTaskModal();
        });
    });

    closeTaskButtons.forEach(function (button) {
        button.addEventListener("click", function (event) {
            event.preventDefault();
            closeTaskModal();
        });
    });

    taskModalOverlay.addEventListener("click", function (event) {
        if (event.target === taskModalOverlay) {
            closeTaskModal();
        }
    });

    document.addEventListener("keydown", function (event) {
        if (
            event.key === "Escape" &&
            taskModalOverlay.classList.contains("open")
        ) {
            closeTaskModal();
        }
    });
});
