from app.workers.domain.embedding_job_fencing import worker_owns_job


def test_worker_owns_job_requires_matching_tokens():
    assert worker_owns_job(job_status="running", job_token="a", held_token="a")
    assert not worker_owns_job(job_status="running", job_token="a", held_token="b")
    assert not worker_owns_job(job_status="queued", job_token="a", held_token="a")


def test_stale_worker_must_not_be_treated_as_owner():
    assert not worker_owns_job(job_status="running", job_token="new", held_token="old")
