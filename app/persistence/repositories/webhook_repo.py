from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.persistence.models.idempotency import IdempotencyRecord
import logging

logger = logging.getLogger(__name__)

class DuplicateEventError(Exception):
    pass

class WebhookRepo:
    def __init__(self, session: Session):
        self.session = session

    def check_idempotency(self, event_id: str) -> None:
        """
        Inserts idempotency record. Raises DuplicateEventError if duplicate.
        Raises IntegrityError for any other constraint failure.
        """
        record = IdempotencyRecord(idempotency_key=event_id, request_hash="N/A", response_status=200)
        self.session.add(record)
        try:
            self.session.flush()
        except IntegrityError as e:
            if hasattr(e.orig, 'diag') and e.orig.diag.constraint_name == 'ix_idempotency_records_idempotency_key':
                logger.info(f"Duplicate event {event_id} detected via idempotency_key")
                self.session.rollback()
                raise DuplicateEventError()
            
            if hasattr(e.orig, 'pgcode') and e.orig.pgcode == '23505' and 'idempotency' in str(e.orig).lower():
                 # Fallback for some drivers if diag isn't fully populated
                 logger.info(f"Duplicate event {event_id} detected via pgcode")
                 self.session.rollback()
                 raise DuplicateEventError()

            # Re-raise genuine errors
            raise
