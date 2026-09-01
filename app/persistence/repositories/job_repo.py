from sqlalchemy.orm import Session
from sqlalchemy import select, update, and_
from datetime import datetime, timedelta
from typing import Optional

from app.persistence.models.recovery import RecoveryJob, JobState
from app.config.settings import WORKER_LEASE_TIMEOUT

class StaleWorkerError(Exception):
    pass

class JobRepository:
    def __init__(self, session: Session):
        self.session = session

    def claim_job(self, worker_id: str) -> Optional[RecoveryJob]:
        """
        Claims a PENDING or expired RUNNING job.
        """
        now = datetime.utcnow()
        lease_threshold = now - timedelta(seconds=WORKER_LEASE_TIMEOUT)

        # Find eligible job
        stmt = select(RecoveryJob).where(
            (RecoveryJob.status == JobState.PENDING) |
            (
                (RecoveryJob.status == JobState.RUNNING) & 
                (RecoveryJob.locked_at < lease_threshold)
            )
        ).with_for_update(skip_locked=True).limit(1)
        
        job = self.session.execute(stmt).scalars().first()
        
        if job:
            job.status = JobState.RUNNING
            job.locked_at = now
            job.locked_by = worker_id
            self.session.flush()
        
        return job

    def safe_update_status(self, job_id: str, worker_id: str, status: JobState, last_error: str = None) -> None:
        """
        Updates a job ONLY if the worker still holds the lease.
        """
        stmt = update(RecoveryJob).where(
            RecoveryJob.id == job_id,
            RecoveryJob.locked_by == worker_id
        ).values(status=status, last_error=last_error)
        
        result = self.session.execute(stmt)
        if result.rowcount == 0:
            raise StaleWorkerError("Worker lost lease or job no longer exists.")
