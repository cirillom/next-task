import type { Task, TaskSummary } from './api/types';

type CompletableTask = Pick<Task | TaskSummary, 'title' | 'unfinished_descendant_count'>;

export function confirmTaskCompletion(task: CompletableTask): boolean {
  const count = task.unfinished_descendant_count;
  if (count <= 0) return true;

  return window.confirm(
    `“${task.title}” has ${count} unfinished task${count === 1 ? '' : 's'} below it. ` +
      `Finishing this task will also finish every unfinished child task in its tree. Continue?`
  );
}
