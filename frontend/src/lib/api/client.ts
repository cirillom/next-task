import type { Member, Status, Tag, Task, TaskInput, User, Workspace } from './types';

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
  login: (email: string, password: string) =>
    request<User>('/api/auth/login', json('POST', { email, password })),
  logout: () => request('/api/auth/logout', json('POST')),
  changePassword: (current_password: string, new_password: string) =>
    request('/api/auth/change-password', json('POST', { current_password, new_password })),

  workspaces: () => request<Workspace[]>('/api/workspaces'),
  createWorkspace: (name: string) =>
    request<Workspace>('/api/workspaces', json('POST', { name })),
  updateWorkspace: (id: number, body: Partial<Pick<Workspace, 'name' | 'scoring_formula'>>) =>
    request<Workspace>(`/api/workspaces/${id}`, json('PATCH', body)),
  members: (id: number) => request<Member[]>(`/api/workspaces/${id}/members`),
  addMember: (id: number, email: string, role: string) =>
    request<Member>(`/api/workspaces/${id}/members`, json('POST', { email, role })),
  updateMember: (id: number, userId: number, role: string) =>
    request<Member>(`/api/workspaces/${id}/members/${userId}`, json('PATCH', { role })),
  removeMember: (id: number, userId: number) =>
    request<void>(`/api/workspaces/${id}/members/${userId}`, json('DELETE')),

  statuses: (id: number) => request<Status[]>(`/api/workspaces/${id}/statuses`),
  createStatus: (id: number, name: string, score_value: number) =>
    request<Status>(`/api/workspaces/${id}/statuses`, json('POST', { name, score_value })),
  updateStatus: (workspaceId: number, statusId: number, body: Partial<Status>) =>
    request<Status>(
      `/api/workspaces/${workspaceId}/statuses/${statusId}`,
      json('PATCH', body)
    ),
  deleteStatus: (workspaceId: number, statusId: number) =>
    request<void>(`/api/workspaces/${workspaceId}/statuses/${statusId}`, json('DELETE')),

  tags: (id: number) => request<Tag[]>(`/api/workspaces/${id}/tags`),
  createTag: (id: number, body: { name: string; description?: string; color?: string }) =>
    request<Tag>(`/api/workspaces/${id}/tags`, json('POST', body)),
  updateTag: (workspaceId: number, tagId: number, body: Partial<Tag>) =>
    request<Tag>(`/api/workspaces/${workspaceId}/tags/${tagId}`, json('PATCH', body)),
  deleteTag: (workspaceId: number, tagId: number) =>
    request<void>(`/api/workspaces/${workspaceId}/tags/${tagId}`, json('DELETE')),
  addTagParent: (workspaceId: number, tagId: number, parent_tag_id: number) =>
    request<Tag>(
      `/api/workspaces/${workspaceId}/tags/${tagId}/parents`,
      json('POST', { parent_tag_id })
    ),
  removeTagParent: (workspaceId: number, tagId: number, parentId: number) =>
    request<Tag>(
      `/api/workspaces/${workspaceId}/tags/${tagId}/parents/${parentId}`,
      json('DELETE')
    ),

  tasks: (workspaceId: number, params: Record<string, string | number | boolean | null> = {}) => {
    const query = new URLSearchParams({ workspace_id: String(workspaceId) });
    for (const [key, value] of Object.entries(params)) {
      if (value !== null && value !== '') query.set(key, String(value));
    }
    return request<Task[]>(`/api/tasks?${query}`);
  },
  task: (id: number) => request<Task>(`/api/tasks/${id}`),
  createTask: (body: TaskInput & { workspace_id: number }) =>
    request<Task>('/api/tasks', json('POST', body)),
  updateTask: (id: number, body: Partial<TaskInput>) =>
    request<Task>(`/api/tasks/${id}`, json('PATCH', body)),
  deleteTask: (id: number) => request<void>(`/api/tasks/${id}`, json('DELETE')),
  finishTask: (id: number) => request<Task>(`/api/tasks/${id}/finish`, json('POST')),
  reopenTask: (id: number) => request<Task>(`/api/tasks/${id}/reopen`, json('POST')),
  blockTask: (id: number, reason: string) =>
    request<Task>(`/api/tasks/${id}/block`, json('POST', { reason })),
  unblockTask: (id: number) => request<Task>(`/api/tasks/${id}/unblock`, json('POST'))
};

