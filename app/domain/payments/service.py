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
from app.domain.observability.audit import create_audit_event
from app.utils.context import get_correlation_id

logger = logging.getLogger(__name__)

class WebhookService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = WebhookRepo(session)

    def process_webhook(self, event: WebhookEvent) -> bool:
        validate_financials(event.amount, event.currency)
        
        try:
            self.repo.check_idempotency(event.event_id)
            
            payment = self.session.query(Payment).filter_by(external_id=event.payment_id).with_for_update().first()
            
            if payment:
                if payment.amount != event.amount or payment.currency.upper() != event.currency.upper() or str(payment.customer_id) != str(event.customer_id):
                    raise ImmutableAttributeError("Core payment attributes are immutable.")
                
                if payment.status in (PaymentState.SUCCEEDED, PaymentState.ABANDONED):
                    logger.info(f"Payment {payment.external_id} is already in terminal state {payment.status}. Silently acknowledging.")
                    
                    create_audit_event(
                        session=self.session,
                        entity_type="PAYMENT",
                        entity_id=str(payment.id),
                        event_type="WEBHOOK_TERMINAL_DOMINANCE_ENFORCED",
                        actor_type="WEBHOOK",
                        payload={"event_id": event.event_id, "type": event.type}
                    )
                    self.session.commit()
                    return True
            else:
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

            if event.type == "payment.failed":
                payment.status = PaymentState.FAILED
                
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
                    
                    # Store correlation_id in job payload!
                    new_job = RecoveryJob(
                        recovery_case_id=new_case.id,
                        job_type="EVALUATE_RECOVERY",
                        scheduled_for=datetime.utcnow(),
                        status=JobState.PENDING,
                        max_attempts=3,
                        available_at=datetime.utcnow() + timedelta(minutes=5),
                        payload={"correlation_id": get_correlation_id()}
                    )
                    self.session.add(new_job)

            elif event.type == "payment.succeeded":
                payment.status = PaymentState.SUCCEEDED
                
                active_cases = self.session.query(RecoveryCase).filter(
                    RecoveryCase.payment_id == payment.id,
                    RecoveryCase.status.notin_([RecoveryState.RECOVERED, RecoveryState.ESCALATED, RecoveryState.STOPPED])
                ).with_for_update().all()
                
                for case in active_cases:
                    case.status = RecoveryState.RECOVERED
                    pending_jobs = self.session.query(RecoveryJob).filter_by(
                        recovery_case_id=case.id, status=JobState.PENDING
                    ).all()
                    for job in pending_jobs:
                        job.status = JobState.CANCELLED

            create_audit_event(
                session=self.session,
                entity_type="PAYMENT",
                entity_id=str(payment.id),
                event_type=f"WEBHOOK_PROCESSED_{event.type.upper()}",
                actor_type="WEBHOOK",
                payload={"event_id": event.event_id, "amount": float(event.amount)}
            )
            self.session.commit()
            return True

        except DuplicateEventError:
            self.session.rollback()
            try:
                # Need to use a new transaction for this observational audit!
                create_audit_event(
                    session=self.session,
                    entity_type="SYSTEM",
                    entity_id=event.event_id,
                    event_type="WEBHOOK_DUPLICATE_REJECTED",
                    actor_type="WEBHOOK",
                    payload={"event_id": event.event_id, "type": event.type}
                )
                self.session.commit()
            except Exception:
                self.session.rollback()
            return True 
        except IntegrityError as e:
            if 'ix_active_recovery_case_per_payment' in str(e.orig):
                logger.info(f"Concurrent active recovery case creation caught for payment {event.payment_id}.")
                self.session.rollback()
                return True
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
