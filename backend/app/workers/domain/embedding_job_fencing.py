"""Worker ownership checks for document embedding jobs."""


def worker_owns_job(*, job_status: str, job_token: str | None, held_token: str | None) -> bool:
    """Return whether the calling worker still owns a running job."""
    if job_status != "running":
        return False
    if not job_token or not held_token:
        return False
    return job_token == held_token
