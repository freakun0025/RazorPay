import logging
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.persistence.models.payment import Payment
from app.persistence.models.recovery import RecoveryCase, RecoveryJob
from app.domain.recovery.states import RecoveryState, PaymentState, JobState

logger = logging.getLogger(__name__)

class AdminOperationsService:
    def __init__(self, session: Session):
        self.session = session

    def get_recovery_case(self, case_id: UUID) -> RecoveryCase:
        case = self.session.query(RecoveryCase).filter_by(id=case_id).first()
        if not case:
            raise HTTPException(status_code=404, detail="Recovery case not found")
        return case

    def stop_recovery_case(self, case_id: UUID) -> RecoveryCase:
        try:
            case = self.session.query(RecoveryCase).filter_by(id=case_id).with_for_update().first()
            if not case:
                raise HTTPException(status_code=404, detail="Recovery case not found")
            
            payment = self.session.query(Payment).filter_by(id=case.payment_id).with_for_update().first()
            if payment and payment.status == PaymentState.SUCCEEDED:
                if case.status != RecoveryState.RECOVERED:
                    case.status = RecoveryState.RECOVERED
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Payment is already SUCCEEDED. Cannot stop case."
                )

            if case.status in [RecoveryState.RECOVERED, RecoveryState.STOPPED, RecoveryState.ESCALATED]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot stop case in terminal state {case.status}"
                )

            case.status = RecoveryState.STOPPED

            pending_jobs = self.session.query(RecoveryJob).filter_by(
                recovery_case_id=case.id, status=JobState.PENDING
            ).all()
            for job in pending_jobs:
                job.status = JobState.CANCELLED
            
            self.session.commit()
            return case

        except HTTPException:
            self.session.rollback()
            raise
        except Exception as e:
            self.session.rollback()
            raise HTTPException(status_code=500, detail=str(e))

    def force_retry_case(self, case_id: UUID) -> RecoveryCase:
        try:
            case = self.session.query(RecoveryCase).filter_by(id=case_id).with_for_update().first()
            if not case:
                raise HTTPException(status_code=404, detail="Recovery case not found")
            
            payment = self.session.query(Payment).filter_by(id=case.payment_id).with_for_update().first()
            if payment and payment.status == PaymentState.SUCCEEDED:
                if case.status != RecoveryState.RECOVERED:
                    case.status = RecoveryState.RECOVERED
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Payment is already SUCCEEDED. Cannot retry case."
                )

            if case.status == RecoveryState.RECOVERED:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot retry case that is already RECOVERED."
                )

            active_jobs = self.session.query(RecoveryJob).filter(
                RecoveryJob.recovery_case_id == case.id,
                RecoveryJob.status.in_([JobState.PENDING, JobState.RUNNING])
            ).all()

            if active_jobs:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Case currently has active pending or running jobs."
                )

            new_job = RecoveryJob(
                recovery_case_id=case.id,
                job_type="EVALUATE_RECOVERY",
                scheduled_for=datetime.utcnow(),
                status=JobState.PENDING,
                max_attempts=3,
                available_at=datetime.utcnow()
            )
            self.session.add(new_job)

            case.status = RecoveryState.OPEN
            
            self.session.commit()
            return case

        except HTTPException:
            self.session.rollback()
            raise
        except Exception as e:
            self.session.rollback()
            raise HTTPException(status_code=500, detail=str(e))
