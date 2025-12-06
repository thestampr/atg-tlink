from __future__ import annotations

from functools import wraps
from threading import Thread
from typing import TYPE_CHECKING, Optional, Union

from schedule import Job

if TYPE_CHECKING:
    from .models import TaskFunction

__all__ = [
    "task",
]

def task(
        schedule: Union[Job, list[Job]], 
        *, 
        name: str = "", 
        first_run: Optional[bool] = False,
        on_success: Optional[function] = None, 
        on_failed: Optional[function] = None,
        on_complete: Optional[function] = None, 
        disabled: bool = False, 
        threaded: bool = False
    ) -> TaskFunction:
    """
    Decorator to mark a function as a scheduled task.

    Parameters
    ----------
    schedule : Job or list[Job]
        The schedule object(s) representing the task's schedule. This can be a single `Job` object or a list of
        `Job` objects.
    name : str, optional
        The name of the task, which can be used for identification or logging purposes. If not provided, it defaults
        to the name of the decorated function.
    first_run : bool, optional
        If set to True, the task will run immediately upon being scheduled for the first time.
    on_success : function, optional
        A function to be called when the decorated task function succeeds (no exceptions raised).
    on_failed : function, optional
        A function to be called when the decorated task function fails (an exception is raised during execution).
    on_complete : function, optional
        A function to be called after the decorated task function completes, whether it succeeded or failed.
    disabled : bool, optional
        Whether the task should be disabled. If `True`, the task will not be executed until it is enabled.
    threaded : bool, optional
        Whether the task should be executed in a separate thread. If `True`, the task will be executed in a separate

    Returns
    -------
    TaskFunction
        The decorated function.

    Notes
    -----
    This decorator is used to mark a function as a scheduled task. The decorated function will be associated with a
    specific schedule represented by a `Job` object from the `schedule` library. When the task manager runs, the
    scheduled tasks will be executed according to their respective schedules.

    If the `on_success`, `on_failed`, or `on_complete` functions are provided, 
    they will be called at the corresponding points in the task's execution. 
    Use these functions to handle specific actions based on the task's execution status.

    Example
    -------
    ::

        from task import *

        @task(every(30).seconds)
        def task_function():
            print("This task is run every 30 seconds.")

        def on_task_success():
            print("Task succeeded")

        def on_task_failure():
            print("Task failed")

        def on_task_completion():
            print("Task completed")

        @task(
            [every(10).seconds, every(1).minutes],
            name="MyTask",
            on_success=on_task_success,
            on_failed=on_task_failure,
            on_complete=on_task_completion,
        )
        def task_function_2_schedule():
            print("This task is run every 10 seconds and every 1 minute.")

        @task(every(10).seconds, threaded=True)
        def task_that_run_and_non_block(self):
            print("I'm running without blocking, my job take 10 seconds")
            time.sleep(10)
            print("I'm done!")

        run_all_tasks()  # Run all tasks
    """

    def decorator(func: TaskFunction) -> TaskFunction:
        if isinstance(schedule, Job):
            func.schedules = [schedule]
        elif isinstance(schedule, list):
            func.schedules = schedule

        func.name = name or func.__name__
        func.is_enable = not disabled
        func.is_running = False
        func.first_run = first_run

        @wraps(func)
        def wrapper(*args, **kwargs_func):
            def worker():
                if func.is_enable and not func.is_running:
                    result = None
                    func.is_running = True
                    try:
                        result = func(*args, **kwargs_func)
                        if on_success: on_success()
                    except:
                        if on_failed: on_failed()
                    if on_complete: on_complete()
                    
                    func.is_running = False
                    return result
                else:
                    return None
                
            if threaded:
                Thread(target=worker).start()
                return None
            else:
                return worker()

        return wrapper
    return decorator
