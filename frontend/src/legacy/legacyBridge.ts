const nativeFetch = window.fetch.bind(window);

const LEGACY_PREFIXES = [
  "/dashboard",
  "/projects",
  "/tasks",
  "/notes",
  "/documents",
  "/focus",
  "/analytics",
  "/notifications",
  "/ai",
  "/login",
  "/register",
  "/logout",
];

const STAGED_HTML_KEY = "lifeos:legacy-parity:staged-html:v1";
const STAGED_HTML_MAX_AGE_MS = 60_000;

let fetchBridgeInstalled = false;

type StagedLegacyHtml = {
  path: string;
  html: string;
  createdAt: number;
};

function currentLogicalPath(): string {
  return `${window.location.pathname}${window.location.search}`;
}

function isLegacyBackendPath(url: URL): boolean {
  if (url.origin !== window.location.origin) return false;
  if (url.pathname.startsWith("/api/")) return false;
  if (url.pathname.startsWith("/static/")) return false;
  if (url.pathname.startsWith("/@") || url.pathname.startsWith("/src/")) return false;
  return LEGACY_PREFIXES.some((prefix) =>
    url.pathname === prefix || url.pathname.startsWith(`${prefix}/`),
  );
}

function proxyUrlFor(url: URL): URL {
  const proxyUrl = new URL("/api/v1/legacy-proxy", window.location.origin);
  url.searchParams.forEach((value, key) => proxyUrl.searchParams.append(key, value));
  return proxyUrl;
}

export function directLegacyProxyUrl(path: string): string {
  const target = new URL(path, window.location.origin);
  const proxy = new URL("/api/v1/legacy-proxy", window.location.origin);
  proxy.searchParams.set("__legacy_path", target.pathname);
  target.searchParams.forEach((value, key) => proxy.searchParams.append(key, value));
  if (target.hash) proxy.hash = target.hash;
  return `${proxy.pathname}${proxy.search}${proxy.hash}`;
}

/**
 * Preserve a direct HTML response from a legacy POST across one hard reload.
 *
 * Some proven Flask workflows intentionally return HTML rather than redirecting
 * (document-type detection is the important example). A normal browser form
 * submission would display that HTML immediately. The React parity host cannot
 * throw that response away and GET the old screen again, because transient UI
 * state such as the detected type would disappear.
 */
export function stageLegacyHtmlForReload(html: string): boolean {
  try {
    const payload: StagedLegacyHtml = {
      path: currentLogicalPath(),
      html,
      createdAt: Date.now(),
    };
    window.sessionStorage.setItem(STAGED_HTML_KEY, JSON.stringify(payload));
    return true;
  } catch (error) {
    console.error("Could not stage the returned LifeOS screen for reload.", error);
    return false;
  }
}

/** Consume a staged POST-rendered page exactly once. */
export function consumeStagedLegacyHtml(): string | null {
  let raw: string | null = null;
  try {
    raw = window.sessionStorage.getItem(STAGED_HTML_KEY);
    if (!raw) return null;

    // Always clear it first so a malformed/stale payload can never loop.
    window.sessionStorage.removeItem(STAGED_HTML_KEY);

    const payload = JSON.parse(raw) as Partial<StagedLegacyHtml>;
    if (
      typeof payload.html !== "string" ||
      typeof payload.path !== "string" ||
      typeof payload.createdAt !== "number"
    ) {
      return null;
    }

    if (payload.path !== currentLogicalPath()) return null;
    if (Date.now() - payload.createdAt > STAGED_HTML_MAX_AGE_MS) return null;

    return payload.html;
  } catch (error) {
    console.warn("Ignoring an invalid staged LifeOS screen.", error);
    try {
      window.sessionStorage.removeItem(STAGED_HTML_KEY);
    } catch {
      // Storage can be unavailable in restricted browser modes.
    }
    return null;
  }
}

/**
 * Follow a legacy redirect without getting stuck on same-page hash redirects.
 *
 * Flask workflows such as Ask Document save state and redirect back to the
 * same document with #ask-document. Assigning only a different hash does not
 * reload React, so the old loading UI would remain forever even though the
 * backend had completed successfully. Force a real reload for same-screen
 * redirects so the newly persisted answer/state is rendered.
 */
export function followLegacyRedirect(redirect: string): void {
  const target = new URL(redirect, window.location.href);
  const current = new URL(window.location.href);

  const sameScreen =
    target.origin === current.origin &&
    target.pathname === current.pathname &&
    target.search === current.search;

  if (sameScreen) {
    const nextUrl = `${target.pathname}${target.search}${target.hash}`;
    window.history.replaceState(window.history.state, "", nextUrl);
    window.location.reload();
    return;
  }

  window.location.assign(target.href);
}

export function installLegacyFetchBridge(): void {
  if (fetchBridgeInstalled) return;
  fetchBridgeInstalled = true;

  window.fetch = async function bridgedFetch(input: RequestInfo | URL, init?: RequestInit) {
    const sourceRequest = input instanceof Request ? input : null;
    const sourceUrl = new URL(
      sourceRequest ? sourceRequest.url : String(input),
      window.location.href,
    );

    if (!isLegacyBackendPath(sourceUrl)) {
      return nativeFetch(input, init);
    }

    const proxy = proxyUrlFor(sourceUrl);
    const headers = new Headers(
      init?.headers ?? (sourceRequest ? sourceRequest.headers : undefined),
    );
    headers.set("X-LifeOS-Legacy-Path", sourceUrl.pathname);

    if (sourceRequest) {
      const method = (init?.method ?? sourceRequest.method ?? "GET").toUpperCase();
      const body =
        method === "GET" || method === "HEAD"
          ? undefined
          : init?.body ?? (await sourceRequest.clone().blob());

      return nativeFetch(proxy, {
        method,
        headers,
        body,
        credentials: init?.credentials ?? sourceRequest.credentials ?? "include",
        cache: init?.cache ?? sourceRequest.cache,
        redirect: "manual",
        signal: init?.signal ?? sourceRequest.signal,
      });
    }

    return nativeFetch(proxy, {
      ...init,
      headers,
      credentials: init?.credentials ?? "include",
      redirect: "manual",
    });
  };
}

export async function fetchLegacyPage(pathname: string, search: string): Promise<Response> {
  return nativeFetch(`/api/v1/legacy-proxy${search}`, {
    method: "GET",
    credentials: "include",
    redirect: "manual",
    headers: {
      Accept: "text/html,application/xhtml+xml",
      "X-LifeOS-Legacy-Path": pathname,
    },
  });
}

export async function submitLegacyForm(form: HTMLFormElement, submitter?: HTMLElement | null): Promise<Response> {
  const method = (form.getAttribute("method") || "GET").toUpperCase();
  const action = new URL(form.getAttribute("action") || window.location.href, window.location.href);
  const formData = new FormData(form);

  if (submitter instanceof HTMLButtonElement && submitter.name) {
    formData.set(submitter.name, submitter.value);
  }
  if (submitter instanceof HTMLInputElement && submitter.name) {
    formData.set(submitter.name, submitter.value);
  }

  if (method === "GET") {
    const destination = new URL(action.href);
    formData.forEach((value, key) => {
      if (typeof value === "string") destination.searchParams.append(key, value);
    });
    window.location.assign(`${destination.pathname}${destination.search}`);
    return new Response(null, { status: 204 });
  }

  return window.fetch(`/api/v1/legacy-proxy${action.search}`, {
    method,
    credentials: "include",
    redirect: "manual",
    headers: {
      Accept: "text/html,application/json",
      "X-LifeOS-Legacy-Path": action.pathname,
    },
    body: formData,
  });
}

export function readLegacyRedirect(response: Response): string | null {
  return response.headers.get("X-LifeOS-Legacy-Redirect");
}

export async function downloadLegacyResource(href: string): Promise<void> {
  const target = new URL(href, window.location.href);
  const response = await nativeFetch(directLegacyProxyUrl(`${target.pathname}${target.search}`), {
    method: "GET",
    credentials: "include",
    headers: { Accept: "*/*" },
  });

  const redirect = readLegacyRedirect(response);
  if (redirect) {
    followLegacyRedirect(redirect);
    return;
  }

  if (!response.ok) {
    throw new Error(`Download failed (${response.status}).`);
  }

  const blob = await response.blob();
  const disposition = response.headers.get("content-disposition") ?? "";
  const filenameMatch = disposition.match(/filename\*?=(?:UTF-8''|\")?([^\";]+)/i);
  const filename = filenameMatch
    ? decodeURIComponent(filenameMatch[1].replace(/^\"|\"$/g, ""))
    : target.pathname.split("/").filter(Boolean).pop() || "lifeos-download";

  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}

export { nativeFetch };
