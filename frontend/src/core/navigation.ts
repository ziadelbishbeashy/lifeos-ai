export function navigate(path: string, replace = false) {
  if (replace) window.location.replace(path);
  else window.location.assign(path);
}

export function currentPath() {
  return window.location.pathname.replace(/\/+$/, "") || "/";
}

export function pathId(pattern: RegExp): number | null {
  const match = currentPath().match(pattern);
  if (!match) return null;
  const value = Number(match[1]);
  return Number.isFinite(value) ? value : null;
}
