from __future__ import annotations

import time
from threading import Thread
from typing import Callable, Union

import __main__
from schedule import cancel_job, run_pending

from .models import TaskFunction

__all__: list[str] = [
    "run_all_tasks", 
    "stop_all_tasks", 
    "enable_task", 
    "disable_task", 
    "task_list", 
]


_R: str = "__tasks_running"
_L: str = "__tasks_list"


def run_all_tasks(__o: object = __main__) -> None:
    """
    Run all scheduled tasks associated with an object.

    Parameters
    ----------
    __o : object, optional
        The object containing the scheduled tasks, by default the main module (__main__).
    """

    if getattr(__o, _R, False): return

    _task_list: list[TaskFunction] = getattr(__o, _L, [])

    def __run() -> None:
        while getattr(__o, _R, True):
            try:
                run_pending()
            except Exception as e:
                print(str(e))
            time.sleep(1)

    for attr_name in dir(__o):
        if attr := getattr(__o, attr_name, None):
            if hasattr(attr, "schedules"):
                attr: TaskFunction
                if attr not in _task_list:
                    _task_list.append(attr)
                    for schedule in attr.schedules:
                        schedule.do(attr)

    setattr(__o, _R, True)
    setattr(__o, _L, _task_list)
    thread = Thread(target=__run, daemon=True)
    thread.start()

def stop_all_tasks(__o: object = __main__) -> None:
    """
    Stop all scheduled tasks associated with an object.

    Parameters
    ----------
    __o : object, optional
        The object containing the scheduled tasks, by default the main module (__main__).
    """

    setattr(__o, _R, False)
    setattr(__o, _L, [])

    for attr_name in dir(__o):
        if attr := getattr(__o, attr_name, None):
            if hasattr(attr, "schedules"):
                attr: TaskFunction
                for schedule in attr.schedules:
                    cancel_job(schedule)

def enable_task(func: Union[TaskFunction, Callable]) -> bool:
    """
    Enable a scheduled task.

    Parameters
    ----------
    func : TaskFunction
        The scheduled task func to enable.

    Returns
    -------
    bool
        True if the task was successfully enabled, False otherwise.
    """

    if hasattr(func, "schedules"):
        func.is_enable = True
        return True
    return False

def disable_task(func: Union[TaskFunction, Callable]) -> bool:
    """
    Disable a scheduled task.

    Parameters
    ----------
    func : TaskFunction
        The scheduled task func to disable.

    Returns
    -------
    bool
        True if the task was successfully disabled, False otherwise.
    """

    if hasattr(func, "schedules"):
        func.is_enable = False
        return True
    return False

def task_list(__o: object = __main__) -> list[TaskFunction]:
    """
    Get a list of all scheduled tasks associated with an object.

    Parameters
    ----------
    __o : object, optional
        The object containing the scheduled tasks, by default the main module (__main__).

    Returns
    -------
    list[TaskFunction]
        A list of all scheduled task functions associated with the object.
    """

    return getattr(__o, _L, [])