import { request } from './client';

export interface GeminiSettings {
  configured: boolean;
  masked_key: string | null;
  model: string;
}

export interface GeminiModel {
  id: string;
  name: string;
}

export interface TextToTaskDraft {
  title: string;
  description: string | null;
  priority: number;
  due_date: string | null;
  assignee_ids: number[];
  existing_tag_ids: number[];
  new_tag_names: string[];
  model: string;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body)
});

export const geminiApi = {
  settings: () => request<GeminiSettings>('/api/integrations/gemini'),
  saveKey: (api_key: string) =>
    request<GeminiSettings>('/api/integrations/gemini', json('PUT', { api_key })),
  models: () => request<GeminiModel[]>('/api/integrations/gemini/models'),
  saveModel: (model: string) =>
    request<GeminiSettings>('/api/integrations/gemini/model', json('PUT', { model })),
  deleteKey: () => request<GeminiSettings>('/api/integrations/gemini', json('DELETE')),
  taskDraft: (workspaceId: number, text: string) =>
    request<TextToTaskDraft>(
      `/api/workspaces/${workspaceId}/task-drafts/from-text`,
      json('POST', { text })
    )
};
