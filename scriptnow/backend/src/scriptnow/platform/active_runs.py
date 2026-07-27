import asyncio


class ActiveRunRegistry:
    """Own process-local tasks for runs that can be actively cancelled."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[object]] = {}

    def track(self, run_id: str, task: asyncio.Task[object]) -> None:
        existing = self._tasks.get(run_id)
        if existing is not None and not existing.done():
            raise RuntimeError(f"run {run_id} already has an active task")
        self._tasks[run_id] = task
        task.add_done_callback(lambda completed: self._discard(run_id, completed))

    def cancel(self, run_id: str) -> bool:
        task = self._tasks.get(run_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    async def cancel_all(self) -> None:
        tasks = [task for task in self._tasks.values() if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _discard(self, run_id: str, completed: asyncio.Task[object]) -> None:
        if self._tasks.get(run_id) is completed:
            self._tasks.pop(run_id, None)
