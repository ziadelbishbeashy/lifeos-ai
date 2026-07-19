(() => {
    "use strict";

    const STORAGE_PENDING = "lifeos-focus-pending-settings";
    const defaultSettings = {
        method: "sprint",
        minutes: 25,
        breakMinutes: 5,
        theme: "mist",
        sound: "none",
        volume: 22,
        fullscreen: false,
        chime: true,
        wakeLock: false,
    };

    const readJSON = (key, fallback) => {
        try {
            return { ...fallback, ...(JSON.parse(localStorage.getItem(key)) || {}) };
        } catch (_) {
            return { ...fallback };
        }
    };

    const writeJSON = (key, value) => {
        try { localStorage.setItem(key, JSON.stringify(value)); } catch (_) { /* storage unavailable */ }
    };

    const methodNames = {
        sprint: "Quick sprint",
        deep: "Deep work",
        flow: "Flow block",
        custom: "Custom session",
    };

    const themeNames = {
        mist: "Mist",
        sage: "Sage",
        lavender: "Lavender",
        sand: "Sand",
    };

    /* =====================================================
       Setup page
       ===================================================== */
    const setupForm = document.getElementById("focusSetupForm");
    if (setupForm) {
        let settings = readJSON("lifeos-focus-default-settings", defaultSettings);

        const durationInput = document.getElementById("focusDurationInput");
        const customWrap = document.getElementById("focusCustomDuration");
        const customInput = document.getElementById("focusCustomMinutes");
        const customLabel = document.getElementById("customMethodMinutes");
        const methodButtons = [...document.querySelectorAll(".focus-method-card")];
        const breakButtons = [...document.querySelectorAll("#setupBreakOptions [data-break]")];
        const themeButtons = [...document.querySelectorAll("#setupThemeOptions [data-focus-theme]")];
        const soundButtons = [...document.querySelectorAll("#setupSoundOptions [data-focus-sound]")];
        const fullscreenInput = document.getElementById("setupFullscreen");
        const chimeInput = document.getElementById("setupChime");
        const wakeLockInput = document.getElementById("setupWakeLock");
        const summary = document.getElementById("focusSetupSummary");

        const applySetupState = () => {
            methodButtons.forEach((button) => {
                button.classList.toggle("active", button.dataset.method === settings.method);
            });
            breakButtons.forEach((button) => {
                button.classList.toggle("active", Number(button.dataset.break) === Number(settings.breakMinutes));
            });
            themeButtons.forEach((button) => {
                button.classList.toggle("active", button.dataset.focusTheme === settings.theme);
            });
            soundButtons.forEach((button) => {
                button.classList.toggle("active", button.dataset.focusSound === settings.sound);
            });

            const minutes = Number(settings.minutes) || 25;
            durationInput.value = minutes;
            customInput.value = settings.method === "custom" ? minutes : (Number(customInput.value) || 40);
            customLabel.textContent = `${customInput.value} min`;
            customWrap.hidden = settings.method !== "custom";
            fullscreenInput.checked = Boolean(settings.fullscreen);
            chimeInput.checked = settings.chime !== false;
            wakeLockInput.checked = Boolean(settings.wakeLock);

            const soundText = settings.sound === "none"
                ? "Silent"
                : settings.sound.charAt(0).toUpperCase() + settings.sound.slice(1);
            summary.textContent = `${minutes}-minute ${methodNames[settings.method].toLowerCase()} · ${settings.breakMinutes}-minute break · ${themeNames[settings.theme]} · ${soundText}`;
        };

        methodButtons.forEach((button) => {
            button.addEventListener("click", () => {
                settings.method = button.dataset.method;
                settings.minutes = Number(button.dataset.minutes) || 25;
                if (settings.method === "custom") {
                    settings.minutes = Number(customInput.value) || 40;
                }
                applySetupState();
            });
        });

        customInput.addEventListener("input", () => {
            const value = Math.min(180, Math.max(5, Number(customInput.value) || 5));
            settings.method = "custom";
            settings.minutes = value;
            customLabel.textContent = `${value} min`;
            durationInput.value = value;
            applySetupState();
        });

        breakButtons.forEach((button) => {
            button.addEventListener("click", () => {
                settings.breakMinutes = Number(button.dataset.break) || 5;
                applySetupState();
            });
        });

        themeButtons.forEach((button) => {
            button.addEventListener("click", () => {
                settings.theme = button.dataset.focusTheme;
                applySetupState();
            });
        });

        soundButtons.forEach((button) => {
            button.addEventListener("click", () => {
                settings.sound = button.dataset.focusSound;
                applySetupState();
            });
        });

        [fullscreenInput, chimeInput, wakeLockInput].forEach((input) => {
            input?.addEventListener("change", () => {
                settings.fullscreen = fullscreenInput.checked;
                settings.chime = chimeInput.checked;
                settings.wakeLock = wakeLockInput.checked;
                applySetupState();
            });
        });

        const taskSelect = document.getElementById("focusTaskSelect");
        const previewProject = document.getElementById("focusPreviewProject");
        const previewPriority = document.getElementById("focusPreviewPriority");
        const previewDeadline = document.getElementById("focusPreviewDeadline");
        const updateTaskPreview = () => {
            const option = taskSelect.options[taskSelect.selectedIndex];
            previewProject.textContent = option?.dataset.project || "General workspace";
            previewPriority.textContent = option?.dataset.priority || "Flexible";
            previewDeadline.textContent = option?.dataset.deadline || "No deadline";
        };
        taskSelect?.addEventListener("change", updateTaskPreview);
        updateTaskPreview();

        setupForm.addEventListener("submit", () => {
            settings.minutes = Number(durationInput.value) || 25;
            settings.fullscreen = fullscreenInput.checked;
            settings.chime = chimeInput.checked;
            settings.wakeLock = wakeLockInput.checked;
            writeJSON(STORAGE_PENDING, settings);
            writeJSON("lifeos-focus-default-settings", settings);

            if (settings.fullscreen && document.documentElement.requestFullscreen && !document.fullscreenElement) {
                document.documentElement.requestFullscreen().catch(() => {});
            }
        });

        applySetupState();
        return;
    }

    /* =====================================================
       Active session
       ===================================================== */
    const session = document.getElementById("focusSession");
    if (!session) return;

    const sessionId = session.dataset.sessionId;
    const sessionStorageKey = `lifeos-focus-session-${sessionId}`;
    let settings = readJSON(sessionStorageKey, null);
    if (!settings || !settings.method) {
        settings = readJSON(STORAGE_PENDING, readJSON("lifeos-focus-default-settings", defaultSettings));
        writeJSON(sessionStorageKey, settings);
        try { localStorage.removeItem(STORAGE_PENDING); } catch (_) { /* ignore */ }
    }

    let totalSeconds = Number(session.dataset.duration || 1500);
    let elapsed = Number(session.dataset.elapsed || 0);
    let status = session.dataset.status;
    let completionHandled = false;
    let breakInterval = null;
    let breakRemaining = Math.max(1, Number(settings.breakMinutes || 5)) * 60;
    let wakeLock = null;

    const timer = document.getElementById("focusTimer");
    const timerCaption = document.getElementById("focusTimerCaption");
    const timerRing = document.getElementById("focusTimerRing");
    const pauseResume = document.getElementById("pauseResumeButton");
    const pauseResumeText = pauseResume?.querySelector("span");
    const extendButton = document.getElementById("extendFocusButton");
    const methodLabel = document.getElementById("focusMethodLabel");
    const completeSheet = document.getElementById("focusCompleteSheet");
    const breakOverlay = document.getElementById("focusBreakOverlay");
    const breakTimer = document.getElementById("focusBreakTimer");

    session.dataset.focusTheme = settings.theme || "mist";
    methodLabel.textContent = methodNames[settings.method] || "Focus session";

    const formatTime = (seconds) => {
        const value = Math.max(0, Math.floor(seconds));
        const minutes = Math.floor(value / 60).toString().padStart(2, "0");
        const secs = (value % 60).toString().padStart(2, "0");
        return `${minutes}:${secs}`;
    };

    const post = async (path, options = {}) => {
        const response = await fetch(path, { method: "POST", ...options });
        let data = {};
        try { data = await response.json(); } catch (_) { /* no JSON */ }
        if (!response.ok) throw new Error(data.message || "The action could not be completed.");
        return data;
    };

    /* Ambient sound engine */
    let audioContext = null;
    let audioSource = null;
    let audioGain = null;
    let soundPlaying = false;

    const stopAmbientSound = () => {
        try { audioSource?.stop(); } catch (_) { /* already stopped */ }
        try { audioSource?.disconnect(); } catch (_) { /* ignore */ }
        try { audioGain?.disconnect(); } catch (_) { /* ignore */ }
        audioSource = null;
        audioGain = null;
        soundPlaying = false;
        updateSoundLabel();
    };

    const buildNoiseBuffer = (context, type) => {
        const seconds = 3;
        const length = context.sampleRate * seconds;
        const buffer = context.createBuffer(1, length, context.sampleRate);
        const data = buffer.getChannelData(0);
        let last = 0;
        for (let i = 0; i < length; i += 1) {
            const white = Math.random() * 2 - 1;
            if (type === "brown") {
                last = (last + 0.02 * white) / 1.02;
                data[i] = last * 3.5;
            } else {
                data[i] = white;
            }
        }
        return buffer;
    };

    const startAmbientSound = async () => {
        const type = settings.sound || "none";
        if (type === "none") {
            openPanel("focusToolsPanel", "focusToolsBackdrop");
            return;
        }

        stopAmbientSound();
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (!AudioCtx) return;
        audioContext = audioContext || new AudioCtx();
        if (audioContext.state === "suspended") await audioContext.resume();

        const source = audioContext.createBufferSource();
        source.buffer = buildNoiseBuffer(audioContext, type === "brown" ? "brown" : "white");
        source.loop = true;

        const gain = audioContext.createGain();
        gain.gain.value = Math.max(0, Math.min(1, Number(settings.volume || 22) / 100));

        if (type === "rain") {
            const highPass = audioContext.createBiquadFilter();
            highPass.type = "highpass";
            highPass.frequency.value = 750;
            const lowPass = audioContext.createBiquadFilter();
            lowPass.type = "lowpass";
            lowPass.frequency.value = 6500;
            source.connect(highPass).connect(lowPass).connect(gain).connect(audioContext.destination);
        } else {
            source.connect(gain).connect(audioContext.destination);
        }

        source.start();
        audioSource = source;
        audioGain = gain;
        soundPlaying = true;
        updateSoundLabel();
    };

    const updateSoundLabel = () => {
        const label = document.getElementById("ambientSoundLabel");
        if (!label) return;
        if ((settings.sound || "none") === "none") {
            label.textContent = "Choose sound";
        } else if (soundPlaying) {
            label.textContent = `${settings.sound} on`;
        } else {
            label.textContent = `Start ${settings.sound}`;
        }
    };

    const playChime = async () => {
        if (settings.chime === false) return;
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (!AudioCtx) return;
        const context = audioContext || new AudioCtx();
        if (context.state === "suspended") await context.resume();
        const now = context.currentTime;
        [523.25, 659.25].forEach((frequency, index) => {
            const oscillator = context.createOscillator();
            const gain = context.createGain();
            oscillator.frequency.value = frequency;
            oscillator.type = "sine";
            gain.gain.setValueAtTime(0, now + index * 0.16);
            gain.gain.linearRampToValueAtTime(0.09, now + index * 0.16 + 0.03);
            gain.gain.exponentialRampToValueAtTime(0.001, now + index * 0.16 + 0.55);
            oscillator.connect(gain).connect(context.destination);
            oscillator.start(now + index * 0.16);
            oscillator.stop(now + index * 0.16 + 0.6);
        });
    };

    const updateSettingsStorage = () => {
        writeJSON(sessionStorageKey, settings);
        writeJSON("lifeos-focus-default-settings", settings);
    };

    const render = () => {
        const remaining = totalSeconds - elapsed;
        timer.textContent = formatTime(Math.abs(remaining));
        timerCaption.textContent = remaining >= 0
            ? (status === "paused" ? "paused" : "remaining")
            : "overtime";
        session.classList.toggle("is-overtime", remaining < 0);
        const ratio = totalSeconds > 0 ? Math.min(1, Math.max(0, elapsed / totalSeconds)) : 0;
        timerRing.style.setProperty("--timer-progress", `${ratio * 360}deg`);
        document.title = `${timer.textContent} · LifeOS Focus`;

        if (remaining <= 0 && !completionHandled) {
            completionHandled = true;
            handleTimerComplete();
        }
    };

    const pauseSession = async () => {
        if (status !== "running") return;
        const data = await post(`/focus/${sessionId}/pause`);
        status = data.status;
        if (typeof data.elapsed_seconds === "number") elapsed = data.elapsed_seconds;
        if (pauseResumeText) pauseResumeText.textContent = "Resume";
        render();
    };

    const resumeSession = async () => {
        if (status !== "paused") return;
        const data = await post(`/focus/${sessionId}/resume`);
        status = data.status;
        if (pauseResumeText) pauseResumeText.textContent = "Pause";
        render();
    };

    const handleTimerComplete = async () => {
        try { await pauseSession(); } catch (_) { /* page may be closing */ }
        playChime();
        completeSheet.hidden = false;
    };

    window.setInterval(() => {
        if (status === "running") {
            elapsed += 1;
            render();
        }
    }, 1000);
    render();
    updateSoundLabel();

    pauseResume?.addEventListener("click", async () => {
        pauseResume.disabled = true;
        try {
            if (status === "paused") await resumeSession();
            else await pauseSession();
        } catch (error) {
            console.error(error);
        } finally {
            pauseResume.disabled = false;
        }
    });

    extendButton?.addEventListener("click", async () => {
        extendButton.disabled = true;
        try {
            const data = await post(`/focus/${sessionId}/extend`);
            totalSeconds = data.planned_minutes * 60;
            completionHandled = elapsed >= totalSeconds;
            extendButton.textContent = "Added 5 minutes";
            window.setTimeout(() => { extendButton.textContent = "+5 minutes"; }, 1200);
            render();
        } catch (error) {
            console.error(error);
        } finally {
            extendButton.disabled = false;
        }
    });

    /* Panels */
    const openPanel = (panelId, backdropId) => {
        const panel = document.getElementById(panelId);
        const backdrop = document.getElementById(backdropId);
        if (!panel || !backdrop) return;
        backdrop.hidden = false;
        panel.classList.add("open");
        panel.setAttribute("aria-hidden", "false");
        document.body.classList.add("focus-panel-open");
    };

    const closePanel = (panelId, backdropId) => {
        const panel = document.getElementById(panelId);
        const backdrop = document.getElementById(backdropId);
        if (!panel || !backdrop) return;
        panel.classList.remove("open");
        panel.setAttribute("aria-hidden", "true");
        window.setTimeout(() => { backdrop.hidden = true; }, 230);
        document.body.classList.remove("focus-panel-open");
    };

    document.getElementById("openFocusTools")?.addEventListener("click", () => openPanel("focusToolsPanel", "focusToolsBackdrop"));
    document.getElementById("openThoughtPanel")?.addEventListener("click", () => {
        openPanel("thoughtPanel", "thoughtPanelBackdrop");
        window.setTimeout(() => document.getElementById("parkThoughtInput")?.focus(), 250);
    });
    document.getElementById("focusToolsBackdrop")?.addEventListener("click", () => closePanel("focusToolsPanel", "focusToolsBackdrop"));
    document.getElementById("thoughtPanelBackdrop")?.addEventListener("click", () => closePanel("thoughtPanel", "thoughtPanelBackdrop"));
    document.querySelectorAll("[data-close-panel]").forEach((button) => {
        button.addEventListener("click", () => {
            const panelId = button.dataset.closePanel;
            const backdropId = panelId === "thoughtPanel" ? "thoughtPanelBackdrop" : "focusToolsBackdrop";
            closePanel(panelId, backdropId);
        });
    });

    /* Theme and sound tools */
    const syncToolSelections = () => {
        document.querySelectorAll("#activeThemeOptions [data-focus-theme]").forEach((button) => {
            button.classList.toggle("active", button.dataset.focusTheme === settings.theme);
        });
        document.querySelectorAll("#activeSoundOptions [data-focus-sound]").forEach((button) => {
            button.classList.toggle("active", button.dataset.focusSound === settings.sound);
        });
        const volume = document.getElementById("focusSoundVolume");
        if (volume) volume.value = settings.volume || 22;
        updateSoundLabel();
    };

    document.querySelectorAll("#activeThemeOptions [data-focus-theme]").forEach((button) => {
        button.addEventListener("click", () => {
            settings.theme = button.dataset.focusTheme;
            session.dataset.focusTheme = settings.theme;
            updateSettingsStorage();
            syncToolSelections();
        });
    });

    document.querySelectorAll("#activeSoundOptions [data-focus-sound]").forEach((button) => {
        button.addEventListener("click", async () => {
            settings.sound = button.dataset.focusSound;
            updateSettingsStorage();
            syncToolSelections();
            if (settings.sound === "none") stopAmbientSound();
            else await startAmbientSound();
        });
    });

    document.getElementById("focusSoundVolume")?.addEventListener("input", (event) => {
        settings.volume = Number(event.target.value);
        if (audioGain) audioGain.gain.value = settings.volume / 100;
        updateSettingsStorage();
    });

    document.getElementById("toggleAmbientSound")?.addEventListener("click", async () => {
        if ((settings.sound || "none") === "none") {
            openPanel("focusToolsPanel", "focusToolsBackdrop");
        } else if (soundPlaying) {
            stopAmbientSound();
        } else {
            await startAmbientSound();
        }
    });
    syncToolSelections();

    /* Fullscreen and wake lock */
    const toggleFullscreen = async () => {
        try {
            if (document.fullscreenElement) await document.exitFullscreen();
            else await document.documentElement.requestFullscreen();
        } catch (_) { /* unsupported or denied */ }
    };
    document.getElementById("focusFullscreenButton")?.addEventListener("click", toggleFullscreen);

    const requestWakeLock = async () => {
        if (!("wakeLock" in navigator)) return false;
        try {
            wakeLock = await navigator.wakeLock.request("screen");
            wakeLock.addEventListener("release", () => {
                wakeLock = null;
                const statusNode = document.getElementById("wakeLockStatus");
                if (statusNode) statusNode.textContent = "Off";
            });
            return true;
        } catch (_) {
            return false;
        }
    };

    document.getElementById("wakeLockButton")?.addEventListener("click", async () => {
        const statusNode = document.getElementById("wakeLockStatus");
        if (wakeLock) {
            await wakeLock.release();
            wakeLock = null;
            settings.wakeLock = false;
            statusNode.textContent = "Off";
        } else {
            const active = await requestWakeLock();
            settings.wakeLock = active;
            statusNode.textContent = active ? "On" : "Unavailable";
        }
        updateSettingsStorage();
    });

    if (settings.wakeLock) {
        requestWakeLock().then((active) => {
            const statusNode = document.getElementById("wakeLockStatus");
            if (statusNode) statusNode.textContent = active ? "On" : "Unavailable";
        });
    }

    /* Parked thoughts */
    const thoughtForm = document.getElementById("parkThoughtForm");
    const thoughtInput = document.getElementById("parkThoughtInput");
    const thoughtFeedback = document.getElementById("parkThoughtFeedback");
    const thoughtCount = document.getElementById("parkedThoughtCount");
    const thoughtList = document.getElementById("parkedThoughtList");
    const emptyThought = document.getElementById("emptyThoughtMessage");

    const bindConvertButton = (button) => {
        button.addEventListener("click", async () => {
            button.disabled = true;
            try {
                await post(`/focus/distractions/${button.dataset.thoughtId}/convert`);
                button.replaceWith(Object.assign(document.createElement("small"), { textContent: "Added to tasks" }));
            } catch (error) {
                button.disabled = false;
                button.textContent = error.message;
            }
        });
    };
    document.querySelectorAll(".convert-thought-button").forEach(bindConvertButton);

    thoughtForm?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const content = thoughtInput.value.trim();
        if (!content) return;
        const submitButton = thoughtForm.querySelector("button[type='submit']");
        submitButton.disabled = true;
        thoughtFeedback.textContent = "";
        try {
            const data = await post(`/focus/${sessionId}/distraction`, {
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ content }),
            });
            thoughtInput.value = "";
            thoughtCount.textContent = data.count;
            thoughtCount.hidden = false;
            emptyThought.hidden = true;

            const article = document.createElement("article");
            article.dataset.thoughtId = data.thought.id;
            const text = document.createElement("p");
            text.textContent = data.thought.content;
            const footer = document.createElement("div");
            const time = document.createElement("span");
            time.textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
            const convert = document.createElement("button");
            convert.type = "button";
            convert.className = "convert-thought-button";
            convert.dataset.thoughtId = data.thought.id;
            convert.textContent = "Convert to task";
            bindConvertButton(convert);
            footer.append(time, convert);
            article.append(text, footer);
            thoughtList.prepend(article);
            thoughtFeedback.textContent = "Saved. Your mind can let it go.";
        } catch (error) {
            thoughtFeedback.textContent = error.message;
        } finally {
            submitButton.disabled = false;
        }
    });

    /* Break timer */
    const showBreak = async () => {
        try { await pauseSession(); } catch (_) { /* keep local break usable */ }
        completeSheet.hidden = true;
        breakRemaining = Math.max(1, Number(settings.breakMinutes || 5)) * 60;
        breakTimer.textContent = formatTime(breakRemaining);
        breakOverlay.hidden = false;
        window.clearInterval(breakInterval);
        breakInterval = window.setInterval(() => {
            breakRemaining -= 1;
            breakTimer.textContent = formatTime(breakRemaining);
            if (breakRemaining <= 0) {
                window.clearInterval(breakInterval);
                playChime();
                breakTimer.textContent = "Ready";
            }
        }, 1000);
    };

    const endBreak = async () => {
        window.clearInterval(breakInterval);
        breakOverlay.hidden = true;
        try { await resumeSession(); } catch (_) { /* page may be closing */ }
    };

    document.getElementById("startBreakButton")?.addEventListener("click", showBreak);
    document.getElementById("completeTakeBreak")?.addEventListener("click", showBreak);
    document.getElementById("skipBreakButton")?.addEventListener("click", endBreak);
    document.getElementById("resumeAfterBreakButton")?.addEventListener("click", endBreak);

    /* Completion and review */
    const reviewModal = document.getElementById("finishFocusModal");
    const openReview = () => {
        completeSheet.hidden = true;
        reviewModal.hidden = false;
        document.body.classList.add("focus-review-open");
        reviewModal.querySelector("input, textarea, select, button")?.focus();
    };
    const closeReview = () => {
        reviewModal.hidden = true;
        document.body.classList.remove("focus-review-open");
    };

    // The main End Session and Review Session actions use normal HTML forms.
    // This keeps them reliable even if another optional browser feature fails.
    if (reviewModal && !reviewModal.hidden) {
        document.body.classList.add("focus-review-open");
    }
    document.getElementById("continueOvertime")?.addEventListener("click", async () => {
        completeSheet.hidden = true;
        await resumeSession();
    });
    reviewModal?.addEventListener("click", (event) => {
        if (event.target === reviewModal) closeReview();
    });

    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        if (reviewModal && !reviewModal.hidden) closeReview();
        else if (document.getElementById("thoughtPanel")?.classList.contains("open")) closePanel("thoughtPanel", "thoughtPanelBackdrop");
        else if (document.getElementById("focusToolsPanel")?.classList.contains("open")) closePanel("focusToolsPanel", "focusToolsBackdrop");
    });

    window.addEventListener("beforeunload", () => {
        stopAmbientSound();
    });
})();
