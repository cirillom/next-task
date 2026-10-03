export interface User {
  id: number;
  email: string;
  display_name: string;
  created_at: string;
}

export interface Status {
  id: number;
  name: string;
  score_value: number;
}

export interface TagSummary {
  id: number;
  name: string;
  color: string | null;
}

export interface Tag extends TagSummary {
  description: string | null;
  direct_task_count: number;
  parents: TagSummary[];
  children: TagSummary[];
  ancestors: TagSummary[];
}

export interface TagMergePreview {
  source_tag_id: number;
  destination_tag_id: number;
  task_assignments: number;
  parent_relationships: number;
  child_relationships: number;
}

export interface Block {
  id: number;
  reason: string | null;
  blocking_task_id: number | null;
  blocking_task: TaskSummary | null;
  blocked_at: string;
  unblocked_at: string | null;
}

export interface TaskSummary {
  id: number;
  title: string;
  finished_at: string | null;
  unfinished_descendant_count: number;
}

export interface Task {
  id: number;
  user_id: number;
  title: string;
  description: string | null;
  status: Status;
  priority: number;
  due_date: string | null;
  last_worked_at: string | null;
  finished_at: string | null;
  parent_task_id: number | null;
  parent_task: TaskSummary | null;
  unfinished_descendant_count: number;
  created_at: string;
  updated_at: string;
  score: number;
  ranking_score: number;
  ranking_source_task_id: number | null;
  ranking_source_score: number | null;
  direct_tags: TagSummary[];
  inherited_tags: TagSummary[];
  current_block: Block | null;
  active_blocks: Block[];
  blocking_history: Block[];
  blocks_tasks: TaskSummary[];
  subtasks: TaskSummary[];
}

export interface TaskInput {
  title: string;
  description: string | null;
  status_id: number;
  priority: number;
  due_date: string | null;
  last_worked_at: string | null;
  parent_task_id: number | null;
  tag_ids: number[];
}

export interface PomodoroSettings {
  focus_minutes: number;
  short_break_minutes: number;
  long_break_minutes: number;
  short_breaks_before_long: number;
  alert_mode: 'notification' | 'alarm';
}

export type PomodoroPhase = 'focus' | 'short-break' | 'long-break';
export type PomodoroState = 'ready' | 'running' | 'ringing';

export interface PomodoroSession {
  tag_id: number | null;
  task_id: number | null;
  phase: PomodoroPhase;
  state: PomodoroState;
  short_breaks_taken: number;
  ends_at: string | null;
  server_now: string;
}
