import uuid
import logging
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.persistence.models.payment import Payment
from app.persistence.models.recovery import RecoveryCase, RecoveryJob
from app.domain.recovery.states import RecoveryState, PaymentState, JobState
from app.domain.observability.audit import create_audit_event
from app.utils.context import get_correlation_id

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
                
                # Observational audit for rejected mutation
                create_audit_event(self.session, "RECOVERY_CASE", str(case.id), "ADMIN_STOP_REJECTED", "ADMIN", {"reason": "PAYMENT_SUCCEEDED"})
                self.session.commit()
                
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Payment is already SUCCEEDED. Cannot stop case."
                )

            if case.status in [RecoveryState.RECOVERED, RecoveryState.STOPPED, RecoveryState.ESCALATED]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot stop case in terminal state {case.status}"
                )

            old_status = case.status.value
            case.status = RecoveryState.STOPPED

            pending_jobs = self.session.query(RecoveryJob).filter_by(
                recovery_case_id=case.id, status=JobState.PENDING
            ).all()
            for job in pending_jobs:
                job.status = JobState.CANCELLED
            
            create_audit_event(self.session, "RECOVERY_CASE", str(case.id), "ADMIN_STOP_CASE", "ADMIN", {"old_status": old_status})
            
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
                
                create_audit_event(self.session, "RECOVERY_CASE", str(case.id), "ADMIN_RETRY_REJECTED", "ADMIN", {"reason": "PAYMENT_SUCCEEDED"})
                self.session.commit()
                
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
                create_audit_event(self.session, "RECOVERY_CASE", str(case.id), "ADMIN_RETRY_REJECTED", "ADMIN", {"reason": "ACTIVE_JOBS_EXIST"})
                self.session.commit()
                
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
                available_at=datetime.utcnow(),
                payload={"correlation_id": get_correlation_id()}
            )
            self.session.add(new_job)

            old_status = case.status.value
            case.status = RecoveryState.OPEN
            
            create_audit_event(self.session, "RECOVERY_CASE", str(case.id), "ADMIN_RETRY_CASE", "ADMIN", {"old_status": old_status})
            
            self.session.commit()
            return case

        except HTTPException:
            self.session.rollback()
            raise
        except Exception as e:
            self.session.rollback()
            raise HTTPException(status_code=500, detail=str(e))
    def get_recovery_analytics(self, start_at: datetime, end_at: datetime) -> dict:
        if start_at >= end_at:
            raise HTTPException(status_code=400, detail="start_at must be before end_at")
            
        from sqlalchemy import select, func, case as sql_case
        from app.persistence.models.recovery import RecoveryAttempt
        
        # We need two aggregates: one on RecoveryCase alone (to avoid multiplying cases by attempts),
        # and one on RecoveryAttempt. Or we can just do two simple queries.
        
        # Query 1: Case aggregates
        case_stmt = select(
            RecoveryCase.currency,
            func.count(RecoveryCase.id).label('total_cases'),
            func.sum(sql_case((RecoveryCase.status == RecoveryState.RECOVERED, 1), else_=0)).label('successful_cases'),
            func.sum(sql_case((RecoveryCase.status.in_([RecoveryState.STOPPED, RecoveryState.ESCALATED]), 1), else_=0)).label('failed_stopped_cases'),
            func.sum(RecoveryCase.amount_at_risk).label('amount_attempted'),
            func.sum(sql_case((RecoveryCase.status == RecoveryState.RECOVERED, RecoveryCase.amount_at_risk), else_=0)).label('amount_recovered')
        ).where(
            RecoveryCase.created_at >= start_at,
            RecoveryCase.created_at < end_at
        ).group_by(RecoveryCase.currency)
        
        case_rows = self.session.execute(case_stmt).all()
        
        # Query 2: Attempt aggregates
        from app.domain.recovery.states import AttemptState
        attempt_stmt = select(
            RecoveryCase.currency,
            func.count(RecoveryAttempt.id).label('total_attempts'),
            func.sum(sql_case((RecoveryAttempt.status == AttemptState.SUCCEEDED, 1), else_=0)).label('successful_attempts'),
            func.sum(sql_case((RecoveryAttempt.status == AttemptState.FAILED, 1), else_=0)).label('failed_attempts')
        ).select_from(RecoveryCase).join(
            RecoveryAttempt, RecoveryCase.id == RecoveryAttempt.recovery_case_id
        ).where(
            RecoveryCase.created_at >= start_at,
            RecoveryCase.created_at < end_at
        ).group_by(RecoveryCase.currency)
        
        attempt_rows = self.session.execute(attempt_stmt).all()
        
        metrics_by_currency = {}
        for row in case_rows:
            currency = row.currency
            total_cases = row.total_cases or 0
            successful_cases = row.successful_cases or 0
            failed_stopped_cases = row.failed_stopped_cases or 0
            amount_attempted = float(row.amount_attempted or 0.0)
            amount_recovered = float(row.amount_recovered or 0.0)
            
            metrics_by_currency[currency] = {
                "total_recovery_cases": total_cases,
                "successful_recovery_cases": successful_cases,
                "failed_or_stopped_recovery_cases": failed_stopped_cases,
                "total_recovery_attempts": 0,
                "successful_recovery_attempts": 0,
                "failed_recovery_attempts": 0,
                "amount_attempted": amount_attempted,
                "amount_recovered": amount_recovered,
                "amount_unrecovered": amount_attempted - amount_recovered,
                "recovery_rate": (amount_recovered / amount_attempted) if amount_attempted > 0 else 0.0,
                "success_rate": (successful_cases / total_cases) if total_cases > 0 else 0.0
            }
            
        for row in attempt_rows:
            currency = row.currency
            if currency in metrics_by_currency:
                metrics_by_currency[currency]["total_recovery_attempts"] = row.total_attempts or 0
                metrics_by_currency[currency]["successful_recovery_attempts"] = row.successful_attempts or 0
                metrics_by_currency[currency]["failed_recovery_attempts"] = row.failed_attempts or 0
                
        create_audit_event(self.session, "ANALYTICS", str(uuid.uuid4()), "ANALYTICS_ACCESSED", "ADMIN", {
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat()
        })
        self.session.commit()
        
        return {
            "start_at": start_at,
            "end_at": end_at,
            "metrics_by_currency": metrics_by_currency
        }


