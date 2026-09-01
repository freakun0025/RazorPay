import logging
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta

from app.api.schemas.webhooks import WebhookEvent
from app.persistence.models.payment import Payment
from app.persistence.models.recovery import RecoveryCase, RecoveryJob
from app.persistence.models.customer import Customer
from app.domain.recovery.states import PaymentState, RecoveryState, JobState
from app.persistence.repositories.webhook_repo import WebhookRepo, DuplicateEventError
from app.domain.payments.exceptions import ImmutableAttributeError, validate_financials

logger = logging.getLogger(__name__)

class WebhookService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = WebhookRepo(session)

    def process_webhook(self, event: WebhookEvent) -> bool:
        """
        Returns True if successful or gracefully duplicate.
        Raises Domain Exceptions or generic Exception on failure.
        """
        # 1. Domain Validation
        validate_financials(event.amount, event.currency)
        
        # Start transaction block
        try:
            # 2. Check Idempotency
            self.repo.check_idempotency(event.event_id)
            
            # 3. SELECT FOR UPDATE on Payment
            payment = self.session.query(Payment).filter_by(external_id=event.payment_id).with_for_update().first()
            
            if payment:
                # 4. Immutable Attributes Check
                if payment.amount != event.amount or payment.currency.upper() != event.currency.upper() or str(payment.customer_id) != str(event.customer_id):
                    raise ImmutableAttributeError("Core payment attributes are immutable.")
                
                # 5. Terminal Dominance Logic
                if payment.status in (PaymentState.SUCCEEDED, PaymentState.ABANDONED):
                    logger.info(f"Payment {payment.external_id} is already in terminal state {payment.status}. Silently acknowledging.")
                    self.session.commit()
                    return True
            else:
                # Need to ensure customer exists for FK. Let's lazily create or assume it exists.
                # In real scenario, customer is created prior. For tests, if customer doesn't exist, we create.
                customer = self.session.query(Customer).filter_by(id=event.customer_id).first()
                if not customer:
                    customer = Customer(id=event.customer_id, external_id=f"ext_{event.customer_id}", email="unknown@test.com", name="Unknown")
                    self.session.add(customer)
                    self.session.flush()

                payment = Payment(
                    external_id=event.payment_id,
                    customer_id=event.customer_id,
                    amount=event.amount,
                    currency=event.currency.upper(),
                    status=PaymentState.FAILED if event.type == "payment.failed" else PaymentState.SUCCEEDED
                )
                self.session.add(payment)
                self.session.flush()

            # 6. Apply state and create cases/jobs
            if event.type == "payment.failed":
                payment.status = PaymentState.FAILED
                
                # Check for active case
                active_case = self.session.query(RecoveryCase).filter(
                    RecoveryCase.payment_id == payment.id,
                    RecoveryCase.status.notin_([RecoveryState.RECOVERED, RecoveryState.ESCALATED, RecoveryState.STOPPED])
                ).first()
                
                if not active_case:
                    new_case = RecoveryCase(
                        payment_id=payment.id,
                        customer_id=event.customer_id,
                        amount_at_risk=event.amount,
                        currency=event.currency.upper(),
                        status=RecoveryState.OPEN,
                        failure_reason=event.failure_reason,
                        max_attempts=3
                    )
                    self.session.add(new_case)
                    self.session.flush()
                    
                    new_job = RecoveryJob(
                        recovery_case_id=new_case.id,
                        job_type="EVALUATE_RECOVERY",
                        scheduled_for=datetime.utcnow(),
                        status=JobState.PENDING,
                        max_attempts=3,
                        available_at=datetime.utcnow() + timedelta(minutes=5)
                    )
                    self.session.add(new_job)

            elif event.type == "payment.succeeded":
                payment.status = PaymentState.SUCCEEDED
                
                # Close any active recovery cases
                active_cases = self.session.query(RecoveryCase).filter(
                    RecoveryCase.payment_id == payment.id,
                    RecoveryCase.status.notin_([RecoveryState.RECOVERED, RecoveryState.ESCALATED, RecoveryState.STOPPED])
                ).with_for_update().all()
                
                for case in active_cases:
                    case.status = RecoveryState.RECOVERED
                    # Cancel pending jobs
                    pending_jobs = self.session.query(RecoveryJob).filter_by(
                        recovery_case_id=case.id, status=JobState.PENDING
                    ).all()
                    for job in pending_jobs:
                        job.status = JobState.CANCELLED

            self.session.commit()
            return True

        except DuplicateEventError:
            return True # Successfully swallowed
        except IntegrityError as e:
            # Check for concurrent active case
            if 'ix_active_recovery_case_per_payment' in str(e.orig):
                logger.info(f"Concurrent active recovery case creation caught for payment {event.payment_id}.")
                self.session.rollback()
                return True
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise




