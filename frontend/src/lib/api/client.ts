import type {
  EmailStatus,
  NextScope,
  PomodoroSession,
  PomodoroSettings,
  Tag,
  TagMergePreview,
  Task,
  TaskInput,
  User
} from './types';
import { get } from 'svelte/store';
import { locale, LocalizedError, message, type Language, type Message, type Values } from '../i18n';

export class ApiError extends LocalizedError {
  constructor(
    translation: Message,
    public status: number
  ) {
    super(translation);
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
    let detailMessage: Message = message('api.httpError', { status: response.status });
    try {
      const body = await response.json();
      const detail = body.detail;
      const problem = Array.isArray(detail) ? detail[0] : body;
      if (typeof problem?.code === 'string') detailMessage = message(problem.code, problem.params);
    } catch {
      // Keep the status-based message for non-JSON failures.
    }
    throw new ApiError(detailMessage, response.status);
  }
  const data = response.status === 204 ? undefined : await response.json();
  return localizeResponse(data) as T;
}

function localizeResponse(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(localizeResponse);
  if (!value || typeof value !== 'object') return value;
  const data = value as Record<string, unknown>;
  if (typeof data.message === 'string' && typeof data.code === 'string') {
    data.message = message(data.code, data.params as Values);
  }
  if (typeof data.scoring_warning === 'string' && typeof data.scoring_warning_code === 'string') {
    data.scoring_warning = message(data.scoring_warning_code, data.scoring_warning_params as Values);
  }
  return value;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body)
});

export const api = {
  me: () => request<User>('/api/auth/me'),
  updateLanguage: (language: Language) => request<User>('/api/auth/language', json('PUT', { language })),
  login: (email: string, password: string) =>
    request<User>('/api/auth/login', json('POST', { email, password })),
  acceptInvitation: (token: string, display_name: string, password: string) =>
    request<{ message: Message }>('/api/auth/invitations/accept', json('POST', { token, display_name, password, language: get(locale) })),
  logout: () => request('/api/auth/logout', json('POST')),
  changePassword: (current_password: string, new_password: string) =>
    request('/api/auth/change-password', json('POST', { current_password, new_password })),
  emailStatus: () => request<EmailStatus>('/api/auth/email'),
  requestEmail: (email: string, current_password: string) =>
    request<EmailStatus>('/api/auth/email', json('POST', { email, current_password })),
  verifyEmail: (token: string) =>
    request<{ message: Message }>('/api/auth/email/verify', json('POST', { token })),
  requestPasswordReset: (email: string) =>
    request<{ message: Message }>('/api/auth/forgot-password', json('POST', { email })),
  resetPassword: (token: string, new_password: string) =>
    request<{ message: Message }>('/api/auth/reset-password', json('POST', { token, new_password })),

  pomodoroSettings: () => request<PomodoroSettings>('/api/pomodoro/settings'),
  updatePomodoroSettings: (body: PomodoroSettings) =>
    request<PomodoroSettings>('/api/pomodoro/settings', json('PUT', body)),
  pomodoroSession: () => request<PomodoroSession | null>('/api/pomodoro/session'),
  createPomodoroSession: (body: {
    tag_id: number | null;
    task_id?: number | null;
    scope?: NextScope;
  }) => request<PomodoroSession>('/api/pomodoro/session', json('POST', body)),
  updatePomodoroSessionTask: (task_id: number | null) =>
    request<PomodoroSession>('/api/pomodoro/session/task', json('PUT', { task_id })),
  updatePomodoroSessionScope: (scope: NextScope, expected_scope: NextScope) =>
    request<PomodoroSession>('/api/pomodoro/session/scope', json('PUT', { scope, expected_scope })),
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

  tags: () => request<Tag[]>('/api/tags'),
  createTag: (
    body: {
      name: string;
      description?: string;
      color?: string;
      score_value?: number;
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
  abandonTask: (id: number) => request<Task>(`/api/tasks/${id}/abandon`, json('POST')),
  restoreTask: (id: number) => request<Task>(`/api/tasks/${id}/restore`, json('POST')),
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
