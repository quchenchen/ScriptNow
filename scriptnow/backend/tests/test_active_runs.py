import asyncio

import pytest

from scriptnow.platform.active_runs import ActiveRunRegistry


@pytest.mark.asyncio
async def test_active_run_registry_cancels_and_releases_completed_task() -> None:
    registry = ActiveRunRegistry()
    started = asyncio.Event()

    async def work() -> None:
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(work())
    registry.track("run-1", task)
    await started.wait()

    assert registry.cancel("run-1") is True
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0)
    assert registry.cancel("run-1") is False


@pytest.mark.asyncio
async def test_active_run_registry_cancels_all_on_shutdown() -> None:
    registry = ActiveRunRegistry()
    tasks = [asyncio.create_task(asyncio.Event().wait()) for _ in range(2)]
    registry.track("run-1", tasks[0])
    registry.track("run-2", tasks[1])

    await registry.cancel_all()

    assert all(task.cancelled() for task in tasks)
