from __future__ import annotations

import re
from typing import TYPE_CHECKING, Callable, Optional

from . import helpers

if TYPE_CHECKING:
    from schedule import Job


class TaskFunction(Callable):
    """
    A representation of a scheduled task function.

    This class is used to encapsulate the behavior and state of a scheduled task function. It contains information
    about the task's name, schedule or schedule list, and its execution status (whether it's running and whether it's
    currently enabled or disabled).

    Attributes
    ----------
    name : str
        The name of the task.
    
    schedules : Optional[list[Job]]
        A list of schedule objects representing multiple execution schedules for the task. This can be `None` if the
        task does not have multiple schedules.

    is_running : bool
        A boolean indicating whether the task is currently running or not.

    is_working : bool
        A boolean indicating whether the task is currently enabled and working. If `True`, the task is enabled and
        will execute according to its schedule(s). If `False`, the task is disabled and will not execute until enabled.

    Methods
    -------
    disable()
        Disable the task, preventing it from executing until it is enabled.

    enable()
        Enable the task, allowing it to execute according to its schedule(s).

    Notes
    -----
    Instances of this class are typically created and managed by the `task` decorator when marking functions as
    scheduled tasks. They provide a structured way to manage the execution of tasks based on their schedules and
    enable or disable them as needed.
    """
    
    name: str

    schedules: Optional[list[Job]]

    is_running: bool
    is_enable: bool

    def disable(self) -> None:
        """
        Disable the task, preventing it from executing until it is enabled.
        """
        self.is_enable = False

    def enable(self) -> None:
        """
        Enable the task, allowing it to execute according to its schedule(s).
        """
        self.is_enable = True


class TaskManager:
    """
    A class to manage scheduling and running tasks using the `schedule` library.

    This class provides functionality to register, schedule, and run tasks using the `schedule` library. The class is
    designed to create a separate thread for running scheduled tasks concurrently.
    """

    def __getitem__(self, name: str) -> Optional[TaskFunction]:
        return self.tasks.get(name, None)
    
    @property
    def tasks(self) -> dict[str, TaskFunction]:
        __to_return = {}
        __tasks = helpers.task_list(self)
        for task in __tasks:
            __to_return[task.name] = task
        return __to_return
    
    @property
    def tasks_detail(self) -> dict[str, list]:
        pattern = r"Every (\d+ [\w ]+) at (\d+:\d+:\d+) do (\w+)\(\) \(last run: \[(.+)\], next run: (.+)\)"

        __to_return = {}
        __tasks = helpers.task_list(self)
        for task in __tasks:
            task_info = {
                "task_times": [],
                "last_run": "",
                "next_run": "",
                "enable": task.is_enable,
                "running": task.is_running,
            }
            for t in task.schedules:
                match = re.search(pattern, repr(t))
                if match:
                    time_name = match.group(1)
                    task_time = match.group(2)
                    task_function = match.group(3)
                    last_run = match.group(4)
                    next_run = match.group(5)

                    task_info["task_times"].append(f"Every {time_name} at {task_time}")

                    task_info["last_run"] = last_run
                    task_info["next_run"] = next_run

            __to_return[task.name] = task_info
        return __to_return


    def run(self) -> None:
        """
        Start running the scheduled tasks in a separate thread.
        """
        
        helpers.run_all_tasks(self)

    def stop(self) -> None:
        """
        Stop the running of scheduled tasks.
        """

        helpers.stop_all_tasks(self)