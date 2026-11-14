import { locale, translate } from './i18n';

// Native browser messages follow the browser language, which may differ from the app.
export function installValidationMessages(): void {
  const owned = new WeakSet<Element>();
  const isField = (element: EventTarget | null): element is HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement =>
    element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element instanceof HTMLSelectElement;
  const clear = (field: EventTarget | null) => {
    if (isField(field) && owned.has(field)) {
      field.setCustomValidity('');
      owned.delete(field);
    }
  };
  document.addEventListener('input', event => clear(event.target));
  document.addEventListener('change', event => clear(event.target));
  locale.subscribe(() => document.querySelectorAll('input, textarea, select').forEach(clear));
  document.addEventListener('invalid', event => {
    const field = event.target;
    if (!isField(field) || field.validity.customError) return; // DateTimeInput owns its date-format errors.
    const validity = field.validity;
    let key = 'validation.invalidValue';
    let count = 0;
    if (validity.valueMissing) key = 'validation.required';
    else if (field instanceof HTMLInputElement && validity.typeMismatch && field.type === 'email') key = 'api.enterAValidEmailAddress';
    else if (field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement) {
      if (validity.tooShort) { key = 'validation.minLength'; count = field.minLength; }
      else if (validity.tooLong) { key = 'validation.maxLength'; count = field.maxLength; }
    }
    field.setCustomValidity(translate(key, {count}));
    owned.add(field);
  }, true);
}
