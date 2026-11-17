# Preserve edits on dismissal

Plan agreed before implementation:

| Surface | Implicit dismissal | Explicit action |
| --- | --- | --- |
| Simple Quick Capture text | Discard it; do not create a draft automatically | Draft task explicitly saves a draft |
| Expanded Quick Capture review | Save a new draft, never activate it | Create activates; Back returns to capture; explicit Cancel discards |
| Existing task editor | Save edits to the same task | Cancel discards |
| Existing draft editor | Save to the same draft without activation | Save as task activates; Cancel discards |
| Nested new task editor | Save a draft without creating an implicit dependency | Existing explicit creation keeps its relationship workflow |
| Tags page | Save before selecting another tag, starting another tag, or navigating away | Cancel discards creation |
| Inline tag creation in task forms | Finish pending valid tag creation before preserving the containing task | Cancel abandons that tag creation |
| Blocking, merging, finishing, abandonment, security settings | Keep existing explicit confirmation/submit behavior | Never execute these actions because of an outside click |
| Search/filter popovers and Focus notes | No new behavior: popovers are not document editors; notes already autosave | Existing semantics |

Backdrop clicks, close icons, Escape, and reference navigation are implicit dismissal. A pure field blur is not dismissal and must not create objects. Unchanged editors close without a write; empty new capture creates nothing. Save failures, conflicts, invalid fields, and in-flight requests keep the editor and its text available. Do not change backend schemas, draft representation, or browser-tab unload guarantees.

Use existing draft/task/tag APIs and guarded description writes. Keep dismissal logic local to the owning editor; do not change generic dialog closing to execute arbitrary submissions. Gate navigation on successful persistence. Prevent duplicate saves while waiting, include pending inline tags, preserve nested tag-parent drafts, and keep explicit cancellation separate.

Verify real backdrop clicks, Escape/close, tag switching and page navigation, unchanged/empty editors, explicit Cancel, draft inactivity, same-task updates, nested tags, duplicate dismissal, invalid fields, failed saves, and guarded-write conflicts. Retain existing keyboard and Markdown regression coverage; use isolated browser fixtures.
