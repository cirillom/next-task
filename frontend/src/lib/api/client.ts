import type {
  PomodoroSession,
  PomodoroSettings,
  Status,
  Tag,
  TagMergePreview,
  Task,
  TaskInput,
  User
} from './types';

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number
  ) {
    super(message);
  }
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: 'same-origin',
    headers: {
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...init.headers
    }
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message = typeof body.detail === 'string' ? body.detail : message;
    } catch {
      // Keep the status-based message for non-JSON failures.
    }
    throw new ApiError(message, response.status);
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body)
});

export const api = {
  me: () => request<User>('/api/auth/me'),
  login: (identifier: string, password: string) =>
    request<User>('/api/auth/login', json('POST', { email: identifier, password })),
  signup: (identifier: string, password: string) =>
    request<User>('/api/auth/signup', json('POST', { identifier, password })),
  logout: () => request('/api/auth/logout', json('POST')),
  changePassword: (current_password: string, new_password: string) =>
    request('/api/auth/change-password', json('POST', { current_password, new_password })),

  pomodoroSettings: () => request<PomodoroSettings>('/api/pomodoro/settings'),
  updatePomodoroSettings: (body: PomodoroSettings) =>
    request<PomodoroSettings>('/api/pomodoro/settings', json('PUT', body)),
  pomodoroSession: () => request<PomodoroSession | null>('/api/pomodoro/session'),
  createPomodoroSession: (body: {
    tag_id: number | null;
    task_id?: number | null;
  }) => request<PomodoroSession>('/api/pomodoro/session', json('POST', body)),
  updatePomodoroSessionTask: (task_id: number | null) =>
    request<PomodoroSession>('/api/pomodoro/session/task', json('PUT', { task_id })),
  startPomodoroPeriod: () =>
    request<PomodoroSession>('/api/pomodoro/session/start', json('POST')),
  skipPomodoroPeriod: () =>
    request<PomodoroSession>('/api/pomodoro/session/skip', json('POST')),
  dismissPomodoroAlarm: () =>
    request<PomodoroSession>('/api/pomodoro/session/dismiss', json('POST')),
  endPomodoroSession: () => request<void>('/api/pomodoro/session', json('DELETE')),

  scoringSettings: () => request<{ scoring_formula: string }>('/api/settings/scoring'),
  updateScoringSettings: (scoring_formula: string) =>
    request<{ scoring_formula: string }>('/api/settings/scoring', json('PUT', { scoring_formula })),
  statuses: () => request<Status[]>('/api/statuses'),
  createStatus: (name: string, score_value: number) =>
    request<Status>('/api/statuses', json('POST', { name, score_value })),
  updateStatus: (statusId: number, body: Partial<Status>) =>
    request<Status>(`/api/statuses/${statusId}`, json('PATCH', body)),
  deleteStatus: (statusId: number) =>
    request<void>(`/api/statuses/${statusId}`, json('DELETE')),

  tags: () => request<Tag[]>('/api/tags'),
  createTag: (
    body: {
      name: string;
      description?: string;
      color?: string;
      parent_tag_id?: number | null;
    }
  ) => request<Tag>('/api/tags', json('POST', body)),
  updateTag: (tagId: number, body: Partial<Tag>) =>
    request<Tag>(`/api/tags/${tagId}`, json('PATCH', body)),
  deleteTag: (tagId: number) => request<void>(`/api/tags/${tagId}`, json('DELETE')),
  addTagParent: (tagId: number, parent_tag_id: number) =>
    request<Tag>(
      `/api/tags/${tagId}/parents`,
      json('POST', { parent_tag_id })
    ),
  removeTagParent: (tagId: number, parentId: number) =>
    request<Tag>(
      `/api/tags/${tagId}/parents/${parentId}`,
      json('DELETE')
    ),
  tagMergePreview: (tagId: number, destinationTagId: number) =>
    request<TagMergePreview>(
      `/api/tags/${tagId}/merge-preview?destination_tag_id=${encodeURIComponent(String(destinationTagId))}`
    ),
  mergeTag: (tagId: number, destinationTagId: number) =>
    request<Tag>(
      `/api/tags/${tagId}/merge`,
      json('POST', { destination_tag_id: destinationTagId })
    ),

  tasks: (
    params: Record<
      string,
      string | number | boolean | null | undefined | readonly (string | number | boolean)[]
    > = {}
  ) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (Array.isArray(value)) {
        for (const item of value) query.append(key, String(item));
      } else if (value !== null && value !== undefined && value !== '') {
        query.set(key, String(value));
      }
    }
    return request<Task[]>(`/api/tasks?${query}`);
  },
  drafts: () => request<Task[]>('/api/drafts'),
  createDraft: (
    body: Pick<TaskInput, 'title'> & Partial<Omit<TaskInput, 'title' | 'priority'>>
  ) => request<Task>('/api/drafts', json('POST', body)),
  task: (id: number) => request<Task>(`/api/tasks/${id}`),
  createTask: (body: TaskInput) =>
    request<Task>('/api/tasks', json('POST', body)),
  updateTask: (id: number, body: Partial<TaskInput>) =>
    request<Task>(`/api/tasks/${id}`, json('PATCH', body)),
  deleteTask: (id: number) => request<void>(`/api/tasks/${id}`, json('DELETE')),
  finishTask: (id: number) => request<Task>(`/api/tasks/${id}/finish`, json('POST')),
  reopenTask: (id: number) => request<Task>(`/api/tasks/${id}/reopen`, json('POST')),
  blockTask: (id: number, body: { reason?: string | null; blocking_task_id?: number | null; unblocked_at?: string | null }) =>
    request<Task>(`/api/tasks/${id}/block`, json('POST', body)),
  unblockTask: (id: number) => request<Task>(`/api/tasks/${id}/unblock`, json('POST')),
  unblockOne: (taskId: number, blockId: number) =>
    request<Task>(`/api/tasks/${taskId}/blocks/${blockId}/unblock`, json('POST')),
  reblockTask: (id: number, unblocked_at: string | null = null) =>
    request<Task>(`/api/tasks/${id}/reblock`, json('POST', { unblocked_at })),
  deleteBlock: (taskId: number, blockId: number) =>
    request<Task>(`/api/tasks/${taskId}/blocks/${blockId}`, json('DELETE'))
};
