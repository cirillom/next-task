export type DescriptionSave = {
  value: string;
  base: string | null;
  state: 'idle' | 'saving' | 'saved' | 'error';
  error: unknown;
  revision: number;
  inFlight: boolean;
  timer: ReturnType<typeof setTimeout> | null;
};

export class DescriptionSaves {
  private drafts = new Map<number, DescriptionSave>();
  private listeners = new Set<(id: number) => void>();

  constructor(private save: (id: number, value: string | null, base: string | null) => Promise<void>) {}

  subscribe(listener: (id: number) => void) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify(id: number) {
    for (const listener of this.listeners) listener(id);
  }

  open(id: number, description: string | null) {
    let draft = this.drafts.get(id);
    if (!draft) {
      draft = { value: description || '', base: description, state: 'idle', error: null, revision: 0, inFlight: false, timer: null };
      this.drafts.set(id, draft);
    } else if (!draft.inFlight && draft.state !== 'saving' && draft.state !== 'error') {
      draft.value = description || '';
      draft.base = description;
      draft.state = 'idle';
    }
    return draft;
  }

  get(id: number) { return this.drafts.get(id); }

  edit(id: number, value: string) {
    const draft = this.drafts.get(id);
    if (!draft) return;
    draft.value = value;
    draft.revision++;
    if (draft.state !== 'error') {
      draft.state = 'saving';
      if (draft.timer) clearTimeout(draft.timer);
      draft.timer = setTimeout(() => this.flush(id), 650);
    }
    this.notify(id);
  }

  flush(id: number, retry = false) {
    const draft = this.drafts.get(id);
    if (!draft) return;
    if (draft.timer) clearTimeout(draft.timer);
    draft.timer = null;
    if (draft.inFlight || (draft.state === 'error' && !retry)) return;
    if (draft.state === 'idle' || draft.state === 'saved') return;
    const value = draft.value || null;
    if (value === draft.base) {
      draft.state = 'saved';
      draft.error = null;
      this.notify(id);
      return;
    }
    const revision = draft.revision;
    draft.inFlight = true;
    draft.state = 'saving';
    draft.error = null;
    this.notify(id);
    void this.save(id, value, draft.base).then(() => {
      if (this.drafts.get(id) !== draft) return;
      draft.base = value;
      draft.inFlight = false;
      if (draft.revision === revision) {
        draft.state = 'saved';
        this.notify(id);
      } else {
        this.flush(id);
      }
    }, (error) => {
      if (this.drafts.get(id) !== draft) return;
      draft.inFlight = false;
      draft.state = 'error';
      draft.error = error;
      this.notify(id);
    });
  }

  resolve(id: number, latest: string | null, keepDraft: boolean) {
    const draft = this.drafts.get(id);
    if (!draft || draft.inFlight) return;
    draft.base = latest;
    if (keepDraft) this.flush(id, true);
    else {
      draft.value = latest || '';
      draft.state = 'idle';
      draft.error = null;
      this.notify(id);
    }
  }

  dirty() {
    return [...this.drafts.values()].some((draft) => draft.inFlight || draft.state === 'saving' || draft.state === 'error');
  }

  clear() {
    for (const draft of this.drafts.values()) if (draft.timer) clearTimeout(draft.timer);
    this.drafts.clear();
  }
}
