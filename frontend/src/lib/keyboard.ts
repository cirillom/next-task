import { translate } from './i18n';

type DialogOptions = { close: () => void; submit?: () => void; save?: () => void; busy?: boolean; navigate?: (next: () => void) => void };
const dialogs: { node: HTMLElement; options: DialogOptions }[] = [];
export const hasDialog = () => dialogs.length > 0;
export function closeTopDialog(): void {
  const current = dialogs.at(-1);
  if (current && !current.options.busy) current.options.close();
}
export const isModified = (event: KeyboardEvent) => event.ctrlKey || event.metaKey || event.altKey;
export const ignoreKey = (event: KeyboardEvent) => event.defaultPrevented || event.isComposing || event.repeat;
export const isSaveKey = (event: KeyboardEvent) => (event.ctrlKey || event.metaKey) && !event.altKey && !event.shiftKey && (event.key === 'Enter' || event.key.toLowerCase() === 's');

export function confirmClose(dirty: boolean, close: () => void, busy = false): void {
  if (!busy && (!dirty || window.confirm(translate('keyboard.discard')))) close();
}

export function navigateFromDialogs(next: () => void): void {
  const open = [...dialogs].reverse();
  function advance(index: number) {
    if (index === open.length) next();
    else open[index].options.navigate?.(() => advance(index + 1));
  }
  advance(0);
}

export function submitEditor(form: HTMLFormElement | null): void {
  if (!form) return;
  const submit = form.querySelector<HTMLButtonElement>('button[type="submit"]');
  if (submit && !submit.disabled) form.requestSubmit(submit);
}

// One dialog owns Escape, save shortcuts, and focus at a time, including nested editors.
export function dialog(node: HTMLElement, options: DialogOptions) {
  const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  node.tabIndex = -1;
  const entry = { node, options };
  dialogs.push(entry);
  const frame = requestAnimationFrame(() => {
    if (dialogs.at(-1) !== entry) return;
    (node.querySelector<HTMLElement>('[autofocus], input:not([type="hidden"]), textarea, select') || node.querySelector<HTMLElement>('button:not(:disabled)') || node).focus();
  });
  function keydown(event: KeyboardEvent) {
    if (dialogs.at(-1) !== entry || event.defaultPrevented || event.isComposing) return;
    if (event.repeat && event.key === 'Enter' && !(event.target instanceof HTMLTextAreaElement) && !(event.target instanceof HTMLElement && event.target.isContentEditable)) {event.preventDefault(); return;}
    if (event.key === 'Escape') {
      event.preventDefault(); event.stopPropagation();
      if (!event.repeat && !entry.options.busy) entry.options.close();
    } else if (isSaveKey(event)) {
      const action = event.key.toLowerCase() === 's' ? entry.options.save || entry.options.submit : entry.options.submit;
      if (action) {
        event.preventDefault(); event.stopPropagation();
        if (!event.repeat && !entry.options.busy) action();
      }
    }
  }
  document.addEventListener('keydown', keydown);
  return {
    update(next: DialogOptions) {entry.options = next;},
    destroy() {
      cancelAnimationFrame(frame);
      const top = dialogs.at(-1) === entry;
      dialogs.splice(dialogs.indexOf(entry), 1);
      document.removeEventListener('keydown', keydown);
      if (top && previous?.isConnected) previous.focus();
    }
  };
}

// Close only the innermost open picker before Escape reaches its parent dialog.
export function pickerEscape(node: HTMLElement, options: { open: () => boolean; close: () => void; capture?: boolean }) {
  function keydown(event: KeyboardEvent) {
    if (event.key !== 'Escape' || ignoreKey(event) || isModified(event) || !options.open()) return;
    event.preventDefault(); event.stopPropagation(); options.close();
  }
  node.addEventListener('keydown', keydown, !!options.capture);
  return {destroy() {node.removeEventListener('keydown', keydown, !!options.capture);}};
}

export function isTyping(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && (target.isContentEditable || !!target.closest('input, textarea, select, [role="textbox"], [role="combobox"], [role="listbox"], [aria-haspopup="listbox"]'));
}

export function dismissible(node: HTMLElement, close: () => void) {
  const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  function keydown(event: KeyboardEvent) {
    if (event.key !== 'Escape' || ignoreKey(event) || hasDialog()) return;
    event.preventDefault(); event.stopPropagation(); close(); previous?.focus();
  }
  document.addEventListener('keydown', keydown);
  return {destroy() {document.removeEventListener('keydown', keydown);}};
}

export function editorKeys(node: HTMLElement, save: () => void) {
  function keydown(event: KeyboardEvent) {
    if (event.defaultPrevented || event.isComposing || hasDialog() || !isSaveKey(event)) return;
    event.preventDefault();
    if (!event.repeat) save();
  }
  node.addEventListener('keydown', keydown);
  return {destroy() {node.removeEventListener('keydown', keydown);}};
}
