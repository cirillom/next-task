export type Role = 'owner' | 'editor' | 'viewer';

export interface User {
  id: number;
  email: string;
  display_name: string;
  created_at: string;
}

export interface Workspace {
  id: number;
  name: string;
  scoring_formula: string | null;
  created_at: string;
  role: Role;
}

export interface Member {
  user_id: number;
  email: string;
  display_name: string;
  role: Role;
}

export interface Status {
  id: number;
  workspace_id: number;
  name: string;
  score_value: number;
}

export interface TagSummary {
  id: number;
  name: string;
  color: string | null;
}

export interface Tag extends TagSummary {
  workspace_id: number;
  description: string | null;
  parents: TagSummary[];
  children: TagSummary[];
  ancestors: TagSummary[];
}

export interface Block {
  id: number;
  reason: string;
  blocked_at: string;
  unblocked_at: string | null;
}

export interface Task {
  id: number;
  created_by_user_id: number;
  creator: User;
  workspace_id: number;
  title: string;
  description: string | null;
  status: Status;
  priority: number;
  due_date: string | null;
  last_worked_at: string | null;
  finished_at: string | null;
  parent_task_id: number | null;
  created_at: string;
  updated_at: string;
  score: number;
  assignees: User[];
  direct_tags: TagSummary[];
  inherited_tags: TagSummary[];
  current_block: Block | null;
  blocking_history: Block[];
  subtasks: Array<{ id: number; title: string; finished_at: string | null }>;
}

export interface TaskInput {
  workspace_id?: number;
  title: string;
  description: string | null;
  status_id: number;
  priority: number;
  due_date: string | null;
  last_worked_at: string | null;
  parent_task_id: number | null;
  assignee_ids: number[];
  tag_ids: number[];
}

export interface PomodoroSettings {
  focus_minutes: number;
  short_break_minutes: number;
  long_break_minutes: number;
  short_breaks_before_long: number;
}
