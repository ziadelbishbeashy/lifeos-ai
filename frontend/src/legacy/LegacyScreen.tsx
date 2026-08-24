import { useEffect, useRef, useState } from "react";
import {
  consumeStagedLegacyHtml,
  directLegacyProxyUrl,
  downloadLegacyResource,
  fetchLegacyPage,
  followLegacyRedirect,
  installLegacyFetchBridge,
  readLegacyRedirect,
  stageLegacyHtmlForReload,
  submitLegacyForm,
} from "./legacyBridge";
import "./legacyScreen.css";

type ScriptDescriptor = {
  src?: string;
  type?: string;
  text?: string;
};

function applyBodyAttributes(source: HTMLElement) {
  const target = document.body;
  [...target.attributes].forEach((attribute) => {
    if (attribute.name !== "style") target.removeAttribute(attribute.name);
  });
  [...source.attributes].forEach((attribute) => {
    target.setAttribute(attribute.name, attribute.value);
  });
}

function syncMetaAndStyles(documentSource: Document) {
  document.title = documentSource.title || "LifeOS AI";

  const csrf = documentSource.querySelector<HTMLMetaElement>('meta[name="csrf-token"]');
  let csrfTarget = document.head.querySelector<HTMLMetaElement>('meta[name="csrf-token"]');
  if (csrf) {
    if (!csrfTarget) {
      csrfTarget = document.createElement("meta");
      csrfTarget.name = "csrf-token";
      document.head.appendChild(csrfTarget);
    }
    csrfTarget.content = csrf.content;
  }

  document.head
    .querySelectorAll('link[data-lifeos-legacy-stylesheet="true"]')
    .forEach((link) => link.remove());

  documentSource
    .querySelectorAll<HTMLLinkElement>('link[rel="stylesheet"][href]')
    .forEach((sourceLink) => {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = sourceLink.getAttribute("href") || "";
      link.dataset.lifeosLegacyStylesheet = "true";
      document.head.appendChild(link);
    });
}

function rewriteNonNavigationalUrls(documentSource: Document) {
  documentSource
    .querySelectorAll<HTMLElement>("[data-db-pdf-url], [data-db-pdf-semantic-search-url]")
    .forEach((element) => {
      ["data-db-pdf-url", "data-db-pdf-semantic-search-url"].forEach((name) => {
        const value = element.getAttribute(name);
        if (value?.startsWith("/")) {
          element.setAttribute(name, directLegacyProxyUrl(value));
        }
      });
    });
}

function collectScripts(documentSource: Document): ScriptDescriptor[] {
  const scripts: ScriptDescriptor[] = [];
  documentSource.querySelectorAll<HTMLScriptElement>("script").forEach((script) => {
    scripts.push({
      src: script.getAttribute("src") || undefined,
      type: script.getAttribute("type") || undefined,
      text: script.src ? undefined : script.textContent || "",
    });
    script.remove();
  });
  return scripts;
}

async function executeScripts(scripts: ScriptDescriptor[]) {
  document
    .querySelectorAll('script[data-lifeos-legacy-runtime="true"]')
    .forEach((script) => script.remove());

  for (const descriptor of scripts) {
    await new Promise<void>((resolve, reject) => {
      const script = document.createElement("script");
      script.dataset.lifeosLegacyRuntime = "true";
      if (descriptor.type) script.type = descriptor.type;

      if (descriptor.src) {
        script.src = descriptor.src;
        script.onload = () => resolve();
        script.onerror = () => reject(new Error(`Could not load ${descriptor.src}`));
        document.body.appendChild(script);
        return;
      }

      script.textContent = descriptor.text || "";
      document.body.appendChild(script);
      resolve();
    });
  }

  // The proven scripts were originally loaded before the browser's real
  // DOMContentLoaded event. React inserts the page after that event, so emit
  // one parity initialization event once the exact markup is mounted.
  document.dispatchEvent(new Event("DOMContentLoaded", { bubbles: true }));
}

export function LegacyScreen() {
  const rootRef = useRef<HTMLDivElement>(null);
  const [html, setHtml] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let cleanupHandlers = () => {};

    async function load() {
      try {
        const stagedHtml = consumeStagedLegacyHtml();
        let pageHtml: string;

        if (stagedHtml !== null) {
          pageHtml = stagedHtml;
        } else {
          const response = await fetchLegacyPage(
            window.location.pathname,
            window.location.search,
          );
          const redirect = readLegacyRedirect(response);
          if (redirect) {
            followLegacyRedirect(redirect);
            return;
          }

          if (!response.ok) {
            throw new Error(`LifeOS could not open this screen (${response.status}).`);
          }

          pageHtml = await response.text();
        }

        const source = new DOMParser().parseFromString(pageHtml, "text/html");
        const scripts = collectScripts(source);
        rewriteNonNavigationalUrls(source);
        syncMetaAndStyles(source);
        applyBodyAttributes(source.body);
        installLegacyFetchBridge();

        if (cancelled) return;
        setHtml(source.body.innerHTML);

        // Wait until React has committed the exact legacy DOM before running
        // the existing browser behavior layer.
        window.setTimeout(async () => {
          if (cancelled) return;
          try {
            await executeScripts(scripts);
            if (cancelled) return;

            const submitHandler = async (event: SubmitEvent) => {
              if (event.defaultPrevented) return;
              const form = event.target;
              if (!(form instanceof HTMLFormElement)) return;
              if (!rootRef.current?.contains(form)) return;

              event.preventDefault();
              try {
                const response = await submitLegacyForm(form, event.submitter);
                const redirect = readLegacyRedirect(response);
                if (redirect) {
                  followLegacyRedirect(redirect);
                  return;
                }

                const contentType = response.headers.get("content-type") || "";
                if (contentType.includes("text/html") && response.ok) {
                  const returnedHtml = await response.text();
                  if (returnedHtml.trim()) {
                    if (!stageLegacyHtmlForReload(returnedHtml)) {
                      throw new Error(
                        "LifeOS received the updated screen but could not preserve it for the React reload.",
                      );
                    }
                    window.location.reload();
                    return;
                  }
                }

                if (contentType.includes("application/json")) {
                  // JSON-returning forms are unusual in the legacy UI. Keep
                  // the page stable and refresh so any server-side state is
                  // reflected without inventing new client behavior.
                  if (response.ok) window.location.reload();
                  return;
                }

                if (response.ok) {
                  window.location.reload();
                }
              } catch (submitError) {
                console.error(submitError);
                window.alert("LifeOS could not complete that action. Please try again.");
              }
            };

            const clickHandler = async (event: MouseEvent) => {
              if (event.defaultPrevented) return;
              const target = event.target;
              if (!(target instanceof Element)) return;
              const anchor = target.closest<HTMLAnchorElement>("a[href]");
              if (!anchor || !rootRef.current?.contains(anchor)) return;

              const url = new URL(anchor.href, window.location.href);
              if (url.origin !== window.location.origin) return;
              if (url.hash && url.pathname === window.location.pathname && url.search === window.location.search) return;

              const isDownload =
                anchor.hasAttribute("download") ||
                url.pathname.includes("/export/") ||
                /\/documents\/\d+\/file$/.test(url.pathname);

              if (!isDownload) return;

              event.preventDefault();
              try {
                await downloadLegacyResource(`${url.pathname}${url.search}`);
              } catch (downloadError) {
                console.error(downloadError);
                window.alert("LifeOS could not download that file. Please try again.");
              }
            };

            document.addEventListener("submit", submitHandler);
            document.addEventListener("click", clickHandler);
            cleanupHandlers = () => {
              document.removeEventListener("submit", submitHandler);
              document.removeEventListener("click", clickHandler);
            };
          } catch (scriptError) {
            console.error(scriptError);
            setError("The screen loaded, but one of its existing UI scripts could not start.");
          }
        }, 0);
      } catch (loadError) {
        console.error(loadError);
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "LifeOS could not load this screen.");
        }
      }
    }

    load();

    return () => {
      cancelled = true;
      cleanupHandlers();
    };
  }, []);

  if (error) {
    return (
      <main className="react-parity-state">
        <div className="react-parity-card">
          <strong>LifeOS UI could not start</strong>
          <p>{error}</p>
          <button type="button" onClick={() => window.location.reload()}>
            Retry
          </button>
        </div>
      </main>
    );
  }

  if (!html) {
    return (
      <main className="react-parity-state" aria-live="polite">
        <div className="react-parity-loader" />
        <strong>Opening LifeOS</strong>
        <span>Restoring your workspace exactly as before…</span>
      </main>
    );
  }

  return <div ref={rootRef} className="react-parity-root" dangerouslySetInnerHTML={{ __html: html }} />;
}
