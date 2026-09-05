import time
import logging
import uuid
import signal
import sys
from sqlalchemy.orm import Session
from app.persistence.database import SessionLocal
from app.workers.executor.execution_service import ExecutionService
import app.config.settings as settings
from app.utils.logger import setup_logging

setup_logging()
logger = logging.getLogger("worker_main")

running = True

def handle_shutdown(signum, frame):
    global running
    logger.info("Shutdown signal received, initiating graceful shutdown...")
    running = False

def main():
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    
    worker_id = f"worker-{uuid.uuid4()}"
    
    # ensure setting exists, fallback to 5.0
    poll_interval = getattr(settings, 'WORKER_POLL_INTERVAL', 5.0)
    
    logger.info(f"Worker {worker_id} starting with poll interval {poll_interval}s")
    
    while running:
        session = SessionLocal()
        try:
            service = ExecutionService(session=session, worker_id=worker_id)
            job_processed = service.process_next_job()
            
            if not job_processed:
                session.close()
                time.sleep(poll_interval)
            else:
                session.close()
                
        except Exception as e:
            logger.error(f"Unexpected error in worker loop: {str(e)}", exc_info=True)
            session.rollback()
            session.close()
            # Avoid tight crash loop
            time.sleep(poll_interval)
            
    logger.info(f"Worker {worker_id} shut down.")

if __name__ == "__main__":
    main()
