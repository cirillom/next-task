import { request } from './client';

export interface McpSettings {
  connector_url: string;
  active_connections: number;
}

export const mcpApi = {
  settings: () => request<McpSettings>('/api/integrations/mcp'),
  revokeAll: () => request<McpSettings>('/api/integrations/mcp', { method: 'DELETE' })
};
