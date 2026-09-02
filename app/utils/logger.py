import logging
import json
from datetime import datetime
from app.utils.context import get_correlation_id
import app.config.settings as settings

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": get_correlation_id(),
        }
        
        # Add extra operational IDs if present in record.__dict__
        for key in ["payment_id", "recovery_case_id", "job_id", "worker_id", "event_type"]:
            if hasattr(record, key):
                log_data[key] = getattr(record, key)
                
        # Scrubbing logic for sensitive data in exception strings or messages
        message = log_data["message"]
        if "sk-" in message or "Bearer " in message:
            log_data["message"] = "[SCRUBBED SENSITIVE DATA]"
            
        if hasattr(record, "exc_info") and record.exc_info:
            log_data["exc_info"] = self.formatException(record.exc_info)
            if "sk-" in log_data["exc_info"] or "Bearer " in log_data["exc_info"]:
                log_data["exc_info"] = "[SCRUBBED SENSITIVE DATA]"
                
        return json.dumps(log_data)

def setup_logging():
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logger = logging.getLogger()
    logger.setLevel(level)
    
    # Clear existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        
    handler = logging.StreamHandler()
    
    if settings.LOG_FORMAT.lower() == "json":
        handler.setFormatter(JSONFormatter())
    else:
        # Fallback for local dev if they want text
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        
    logger.addHandler(handler)
    
    # Prevent noisy libraries from cluttering
    logging.getLogger("httpx").setLevel(logging.WARNING)

def get_logger(name: str):
    return logging.getLogger(name)
