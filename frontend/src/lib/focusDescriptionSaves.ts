import { api } from './api/client';
import { DescriptionSaves } from './descriptionSaves';

export const focusDescriptionSaves = new DescriptionSaves(async (id, description, expected_description) => {
  await api.updateTask(id, { description, expected_description });
});

if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', (event) => {
    if (focusDescriptionSaves.dirty()) event.preventDefault();
  });
}
