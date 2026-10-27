from shoal.tasks.jobs import Job, MemoryJobStore


def job(job_id: str, due: float, name: str = "reminder") -> Job:
    return Job(id=job_id, name=name, due=due)


async def test_jobs_are_claimed_earliest_first_up_to_the_limit() -> None:
    store = MemoryJobStore()
    for job_id, due in (("c", 30), ("a", 10), ("b", 20), ("later", 99)):
        await store.add(job(job_id, due))
    assert not store.shared
    assert await store.next_due() == 10
    assert [claimed.id for claimed in await store.claim(50, 2)] == ["a", "b"]
    assert [claimed.id for claimed in await store.claim(50, 10)] == ["c"]
    assert await store.next_due() == 99
    assert await store.get("a") is None


async def test_replacing_or_cancelling_a_job_leaves_no_ghost_in_the_order() -> None:
    store = MemoryJobStore()
    await store.add(job("a", 10))
    await store.add(job("a", 40))  # moved later
    await store.add(job("b", 20))
    assert await store.cancel("b")
    assert not await store.cancel("b")
    assert await store.next_due() == 40
    assert await store.claim(30, 10) == []
    assert [claimed.due for claimed in await store.claim(40, 10)] == [40]
    assert await store.next_due() is None


async def test_jobs_are_listed_by_name() -> None:
    store = MemoryJobStore()
    await store.add(job("a", 1, "reminder"))
    await store.add(job("b", 2, "digest"))
    assert [listed.id for listed in await store.jobs("digest")] == ["b"]
    assert len(await store.jobs()) == 2
    await store.done(job("a", 1))  # claiming already removed it: nothing else to do
