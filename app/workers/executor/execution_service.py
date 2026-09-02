from app.utils.context import get_correlation_id
from app.domain.observability.audit import create_audit_event
import logging
import uuid
from sqlalchemy.orm import Session
from app.persistence.models.recovery import RecoveryJob, JobState, RecoveryAttempt, AttemptState, RecoveryCase
from app.persistence.models.payment import Payment, PaymentState
from app.persistence.repositories.job_repo import JobRepository, StaleWorkerError
from app.integrations.payment_gateway.mock_client import MockGatewayClient, GatewayTimeoutError
from datetime import datetime, timedelta

from app.ai.contracts import RecoveryDecisionContext, RecoveryDecision
from app.ai.gateway.provider import NemotronProvider
from app.ai.exceptions import AIDecisionError

logger = logging.getLogger(__name__)

class ExecutionService:
    def __init__(self, session: Session, worker_id: str):
        self.session = session
        self.worker_id = worker_id
        self.job_repo = JobRepository(session)
        self.gateway = MockGatewayClient()

    def process_next_job(self) -> bool:
        self.session.begin() # explicitly begin
        try:
            job = self.job_repo.claim_job(self.worker_id)
            if not job:
                self.session.rollback()
                return False
                
            if job.payload and "correlation_id" in job.payload:
                from app.utils.context import set_correlation_id
                set_correlation_id(job.payload["correlation_id"])
                
            job_type = job.job_type
            
            if job_type == "EVALUATE_RECOVERY":
                return self._process_evaluate_recovery(job)
            elif job_type == "EXECUTE_CHARGE":
                return self._process_execute_charge(job)
            else:
                self.session.rollback()
                return False
        except Exception:
            self.session.rollback()
            raise

    def _process_evaluate_recovery(self, job) -> bool:
        try:
            case = self.session.query(RecoveryCase).filter_by(id=job.recovery_case_id).with_for_update().first()
            payment = self.session.query(Payment).filter_by(id=case.payment_id).with_for_update().first()

            if payment.status == PaymentState.SUCCEEDED:
                job.status = JobState.CANCELLED
                create_audit_event(self.session, "RECOVERY_JOB", str(job.id), "JOB_CANCELLED", "WORKER", {"reason": "payment_already_succeeded"})
                self.session.commit()
                return True

            days_since = (datetime.utcnow() - case.started_at).days
            
            context = RecoveryDecisionContext(
                failure_reason=case.failure_reason,
                attempt_count=job.attempt_count,
                days_since_failure=days_since,
                amount=float(case.amount_at_risk),
                currency=case.currency
            )
            job_id = job.id
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        # NETWORK BOUNDARY
        try:
            provider = NemotronProvider()
            decision = provider.decide(context)
        except AIDecisionError as e:
            self._finalize_evaluate_error(job_id, str(e))
            return True
        except Exception as e:
            self._finalize_evaluate_error(job_id, str(e))
            return True

        # TX2
        self._finalize_evaluate_decision(job_id, decision)
        return True

    def _finalize_evaluate_error(self, job_id, error_msg):
        self.session.begin()
        try:
            job = self.session.query(RecoveryJob).filter_by(id=job_id).first()
            if not job or job.locked_by != self.worker_id:
                raise StaleWorkerError("Lost lease")
            job.status = JobState.FAILED
            job.last_error = error_msg
            
            case = self.session.query(RecoveryCase).filter_by(id=job.recovery_case_id).first()
            if job.attempt_count < job.max_attempts:
                self.session.add(RecoveryJob(
                    recovery_case_id=case.id,
                    job_type="EVALUATE_RECOVERY",
                    status=JobState.PENDING,
                    scheduled_for=datetime.utcnow(),
                    available_at=datetime.utcnow() + timedelta(minutes=15),
                    max_attempts=job.max_attempts,
                    attempt_count=job.attempt_count,
                    payload={"correlation_id": get_correlation_id()}
                ))
            else:
                from app.persistence.models.recovery import RecoveryState
                case.status = RecoveryState.STOPPED
                create_audit_event(self.session, "RECOVERY_JOB", str(job.id), "AI_EVALUATION_FAILED", "WORKER", {"error": str(error)})
                
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def _finalize_evaluate_decision(self, job_id, decision: RecoveryDecision):
        self.session.begin()
        try:
            job = self.session.query(RecoveryJob).filter_by(id=job_id).first()
            if not job or job.locked_by != self.worker_id:
                raise StaleWorkerError("Lost lease")
                
            case = self.session.query(RecoveryCase).filter_by(id=job.recovery_case_id).with_for_update().first()
            payment = self.session.query(Payment).filter_by(id=case.payment_id).with_for_update().first()

            if payment.status == PaymentState.SUCCEEDED:
                job.status = JobState.CANCELLED
                create_audit_event(self.session, "RECOVERY_JOB", str(job.id), "JOB_CANCELLED", "WORKER", {"reason": "payment_already_succeeded"})
                self.session.commit()
                return

            from app.persistence.models.recovery import RecoveryDecision as DBDecision
            db_dec = DBDecision(
                recovery_case_id=case.id,
                decision_source="AI",
                action_type=decision.action,
                parameters_json={"confidence": decision.confidence},
                reason=decision.reason,
                policy_result="APPROVED"
            )
            self.session.add(db_dec)
            create_audit_event(self.session, "RECOVERY_JOB", str(job.id), "AI_EVALUATION_COMPLETED", "WORKER", {"action": decision.action, "confidence": decision.confidence})
            
            job.status = JobState.SUCCEEDED
            
            if decision.action == "CHARGE":
                self.session.add(RecoveryJob(
                    recovery_case_id=case.id,
                    job_type="EXECUTE_CHARGE",
                    status=JobState.PENDING,
                    scheduled_for=datetime.utcnow(),
                    available_at=datetime.utcnow(),
                    max_attempts=job.max_attempts,
                    attempt_count=job.attempt_count,
                    payload={"correlation_id": get_correlation_id()}
                ))
            elif decision.action == "ABORT":
                from app.persistence.models.recovery import RecoveryState
                case.status = RecoveryState.STOPPED
            elif decision.action == "DELAY":
                self.session.add(RecoveryJob(
                    recovery_case_id=case.id,
                    job_type="EVALUATE_RECOVERY",
                    status=JobState.PENDING,
                    scheduled_for=datetime.utcnow(),
                    available_at=datetime.utcnow() + timedelta(days=1),
                    max_attempts=job.max_attempts,
                    attempt_count=job.attempt_count,
                    payload={"correlation_id": get_correlation_id()}
                ))
                
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def _process_execute_charge(self, job) -> bool:
        try:
            case = self.session.query(RecoveryCase).filter_by(id=job.recovery_case_id).with_for_update().first()
            payment = self.session.query(Payment).filter_by(id=case.payment_id).with_for_update().first()

            if payment.status == PaymentState.SUCCEEDED:
                job.status = JobState.CANCELLED
                create_audit_event(self.session, "RECOVERY_JOB", str(job.id), "JOB_CANCELLED", "WORKER", {"reason": "payment_already_succeeded"})
                self.session.commit()
                return True

            attempt = None
            if job.attempt_id:
                attempt = self.session.query(RecoveryAttempt).filter_by(id=job.attempt_id).first()

            if not attempt:
                attempt = RecoveryAttempt(
                    id=uuid.uuid4(),
                    recovery_case_id=case.id,
                    attempt_number=job.attempt_count + 1,
                    action_type="CHARGE",
                    status=AttemptState.RUNNING
                )
                self.session.add(attempt)
                self.session.flush()
                job.attempt_id = attempt.id
                job.attempt_count = attempt.attempt_number

            idem_key = f"{payment.external_id}_attempt_{attempt.attempt_number}"
            pay_amount = float(payment.amount)
            pay_currency = payment.currency
            pay_cust = payment.customer_id
            is_ambiguous = attempt.status in (AttemptState.AMBIGUOUS, AttemptState.RUNNING)
            job_id = job.id
            attempt_id = attempt.id
            
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        # NETWORK BOUNDARY
        if is_ambiguous:
            recon = self.gateway.verify_payment_status(idem_key)
            if recon.get("status") == "not_found":
                is_ambiguous = False
            else:
                self._finalize_job(job_id, attempt_id, recon)
                return True

        if not is_ambiguous:
            try:
                res = self.gateway.charge(idem_key, pay_amount, pay_currency, pay_cust)
                self._finalize_job(job_id, attempt_id, res)
            except GatewayTimeoutError:
                self._finalize_ambiguous(job_id, attempt_id)
            except Exception as e:
                self._finalize_job(job_id, attempt_id, {"status": "failed", "error": str(e)})

        return True

    def _finalize_job(self, job_id, attempt_id, result):
        self.session.begin()
        try:
            job = self.session.query(RecoveryJob).filter_by(id=job_id).first()
            if not job or job.locked_by != self.worker_id:
                raise StaleWorkerError("Lost lease")
            job.status = JobState.SUCCEEDED
            
            attempt = self.session.query(RecoveryAttempt).filter_by(id=attempt_id).first()
            case = self.session.query(RecoveryCase).filter_by(id=attempt.recovery_case_id).first()
            payment = self.session.query(Payment).filter_by(id=case.payment_id).first()

            if result.get("status") == "succeeded":
                attempt.status = AttemptState.SUCCEEDED
                payment.status = PaymentState.SUCCEEDED
                create_audit_event(self.session, "RECOVERY_JOB", str(job.id), "CHARGE_EXECUTION_COMPLETED", "WORKER", {"status": "succeeded"})
                from app.persistence.models.recovery import RecoveryState
                case.status = RecoveryState.RECOVERED
            else:
                attempt.status = AttemptState.FAILED
                create_audit_event(self.session, "RECOVERY_JOB", str(job.id), "CHARGE_EXECUTION_FAILED", "WORKER", {"status": "failed"})
                if job.attempt_count < job.max_attempts:
                    self.session.add(RecoveryJob(
                        recovery_case_id=case.id,
                        job_type="EVALUATE_RECOVERY",
                        status=JobState.PENDING,
                        scheduled_for=datetime.utcnow(),
                        available_at=datetime.utcnow(),
                        max_attempts=job.max_attempts,
                        attempt_count=job.attempt_count,
                    payload={"correlation_id": get_correlation_id()}
                ))
                else:
                    from app.domain.recovery.states import RecoveryState
                    case.status = RecoveryState.STOPPED
                    create_audit_event(self.session, "RECOVERY_CASE", str(case.id), "CHARGE_EXHAUSTED", "WORKER", {"reason": "max_attempts_reached"})
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def _finalize_ambiguous(self, job_id, attempt_id):
        self.session.begin()
        try:
            job = self.session.query(RecoveryJob).filter_by(id=job_id).first()
            if not job or job.locked_by != self.worker_id:
                raise StaleWorkerError("Lost lease")
            job.status = JobState.PENDING
            attempt = self.session.query(RecoveryAttempt).filter_by(id=attempt_id).first()
            attempt.status = AttemptState.AMBIGUOUS
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

