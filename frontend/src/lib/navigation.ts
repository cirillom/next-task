export function reloadApp(href = '/#/'): void {
  window.history.replaceState(null, '', href);
  window.location.reload();
}
