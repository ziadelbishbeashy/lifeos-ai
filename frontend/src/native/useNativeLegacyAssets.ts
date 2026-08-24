import { useEffect, useLayoutEffect } from "react";

const styles = [
  "/static/css/style.css?v=phase6-project-aware-1",
  "/static/css/theme-v2.css?v=focus-studio-e3-action-center",
  "/static/css/project-studio.css?v=project-studio-e5",
];

export function useNativeLegacyAssets(ready: boolean, notificationUser?: number) {
  useLayoutEffect(() => {
    document.title = "Projects | LifeOS AI";
    document.body.className = "app-body studio-theme";

    const links = styles.map((href) => {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = href;
      link.dataset.lifeosNativeStylesheet = "true";
      document.head.appendChild(link);
      return link;
    });

    return () => {
      links.forEach((link) => link.remove());
    };
  }, []);

  useEffect(() => {
    if (notificationUser != null) {
      document.body.dataset.notificationUser = String(notificationUser);
    }
    return () => {
      delete document.body.dataset.notificationUser;
    };
  }, [notificationUser]);

  useEffect(() => {
    if (!ready) return;

    const oldRuntime = document.querySelector('script[data-lifeos-native-runtime="true"]');
    oldRuntime?.remove();

    const script = document.createElement("script");
    script.src = "/static/js/main.js?v=phase5-focus-1";
    script.dataset.lifeosNativeRuntime = "true";
    script.onload = () => {
      // main.js was written for server-rendered pages and registers its
      // initializers on DOMContentLoaded. React mounted the parity DOM later,
      // so emit the same initialization event once the native page is ready.
      document.dispatchEvent(new Event("DOMContentLoaded", { bubbles: true }));
    };
    document.body.appendChild(script);

    return () => script.remove();
  }, [ready]);
}
