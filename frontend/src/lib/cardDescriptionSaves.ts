import { api, ApiError } from './api/client';
import type { Task } from './api/types';

type Attempt = { id: number; base: string | null; value: string };
type State = { pending: Attempt | null; busy: boolean; error: unknown; conflict: boolean; latest: Task | null };

export class CardDescriptionSaves {
  private states = new Map<number, State>();
  private listeners = new Set<() => void>();

  constructor(private update: typeof api.updateTask, private load: typeof api.task) {}
  subscribe(listener: () => void) { this.listeners.add(listener); return () => this.listeners.delete(listener); }
  private notify() { for (const listener of this.listeners) listener(); }
  get(id: number) { return this.states.get(id); }

  async save(attempt: Attempt) {
    const state = this.states.get(attempt.id) || {pending: null, busy: false, error: null, conflict: false, latest: null};
    if (state.busy) return null;
    this.states.set(attempt.id, state);
    Object.assign(state, {pending: attempt, busy: true, error: null, conflict: false});
    this.notify();
    try {
      const updated = await this.update(attempt.id, {description: attempt.value, expected_description: attempt.base});
      if (this.states.get(attempt.id) !== state) return null;
      state.pending = null;
      state.latest = updated;
      return updated;
    } catch (error) {
      if (this.states.get(attempt.id) !== state) return null;
      state.error = error;
      state.conflict = error instanceof ApiError && error.status === 409;
      if (state.conflict) {
        try {
          const latest = await this.load(attempt.id);
          if (this.states.get(attempt.id) === state) state.latest = latest;
        } catch { /* Keep the attempted text available. */ }
      }
      return null;
    } finally {
      if (this.states.get(attempt.id) === state) { state.busy = false; this.notify(); }
    }
  }

  discard(id: number) {
    const state = this.states.get(id);
    if (!state || state.busy) return;
    state.pending = null; state.error = null; state.conflict = false;
    this.notify();
  }
  acknowledge(task: Task) {
    const state = this.states.get(task.id);
    if (state && !state.pending && state.latest?.description === task.description) this.states.delete(task.id);
  }
  clear() { this.states.clear(); this.notify(); }
}

export const cardDescriptionSaves = new CardDescriptionSaves(api.updateTask, api.task);
