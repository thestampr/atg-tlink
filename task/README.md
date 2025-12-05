# Task Utilities

Utilities under `task/` wrap the [`schedule`](https://schedule.readthedocs.io/) library with a decorator-driven API, helper functions, and a small manager class so background jobs can live next to your application code.

## Installation

```cmd
pip install -r task/requirements.txt
```

The only runtime dependency is `schedule`.

## Quick Start

```python
from schedule import every
from task import TaskManager, task

manager = TaskManager()

@task(
    schedule=every(30).seconds,
    name="sample",
    threaded=True,
    on_success=lambda: print("done"),
)
def pull_remote_state():
    print("syncing...")

if __name__ == "__main__":
    manager.run()      # spin up the scheduler loop in a background thread
    input("Press Enter to stop\n")
    manager.stop()
```

Define functions with `@task`, then either call `run_all_tasks()` (from `task.helpers`) or instantiate `TaskManager` to auto-discover and run them.

## `task.decorators`

`task.decorator.task()` accepts both single `Job` objects and lists of jobs, letting a function run on multiple schedules:

| Argument | Description |
| --- | --- |
| `schedule` | `schedule.Job` or list of jobs returned by `schedule.every(...)`. Required. |
| `name` | Optional task name; defaults to `func.__name__`. |
| `on_success`, `on_failed`, `on_complete` | Optional callbacks fired after execution. |
| `disabled` | Start disabled without deleting the schedule. |
| `threaded` | Run the body in a separate thread to avoid blocking other jobs. |

During execution `task()` guards against concurrent runs (`is_running`) and only executes when `is_enable` is `True`. The decorator stores metadata on the wrapped function so helper utilities can inspect or toggle it later.

## `task.helpers`

Helpers operate on any module-like object (defaults to `__main__`).

- `run_all_tasks(obj=__main__)`: discovers every attribute decorated with `@task`, registers its schedules with `schedule`, and starts a daemon thread that calls `schedule.run_pending()` every second.
- `stop_all_tasks(obj=__main__)`: flips the internal running flag and cancels every registered job.
- `enable_task(func)` / `disable_task(func)`: toggles an individual task at runtime.
- `task_list(obj=__main__)`: returns the cached list of discovered task functions.

Because the scheduler loop runs on a dedicated thread, your main thread stays responsive.

## `task.models`

### `TaskFunction`

A light wrapper typing alias used by the decorator. Each decorated function carries:

- `name`: friendly identifier
- `schedules`: list of `schedule.Job`
- `is_running`: whether the job is currently executing
- `is_enable`: runtime toggle, plus `enable()` / `disable()` helpers

### `TaskManager`

Convenience facade that uses the helpers internally.

Key members:

- `run()` / `stop()`: start or stop the scheduler background loop.
- `tasks`: dict keyed by task name exposing the underlying functions.
- `tasks_detail`: parsed metadata (last/next run, human readable cadence, flags) derived from `repr(job)`; useful for dashboards or health endpoints.
- `__getitem__(name)`: fetch a task by name.

Use `TaskManager` when you want an object-oriented holder for jobs (e.g., inside a Flask app factory).

## Tips

- Combine multiple schedules by passing a list: `@task([every(10).seconds, every().hour])`.
- Long-running tasks should set `threaded=True` so they do not block the scheduler loop.
- Wrap network calls with your own retry / logging inside the `on_success`/`on_failed` callbacks.
- Call `stop_all_tasks()` or `TaskManager.stop()` during shutdown to cancel pending jobs cleanly.
