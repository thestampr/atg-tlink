from task import *
import time

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
def task_that_run_and_non_block():
    print("I'm running without blocking, my job take 10 seconds")
    time.sleep(10)
    print("I'm done!")

run_all_tasks()  # Run all tasks
input("Press Enter to stop...\n")  # Keep the script running
stop_all_tasks()  # Stop all tasks before exiting