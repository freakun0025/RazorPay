import logging
import json
import re
from datetime import datetime
from app.utils.context import get_correlation_id
import app.config.settings as settings

class JSONFormatter(logging.Formatter):
    def _scrub_string(self, text: str) -> str:
        if not isinstance(text, str):
            return text
        # Regex to match bearer tokens and sk- keys
        text = re.sub(r'Bearer\s+[a-zA-Z0-9_\-\.]+', 'Bearer [SCRUBBED]', text)
        text = re.sub(r'sk-[a-zA-Z0-9_\-\.]+', 'sk-[SCRUBBED]', text)
        return text

    def format(self, record):
        message = record.getMessage()
        
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": self._scrub_string(message),
            "correlation_id": get_correlation_id(),
        }
        
        for key in ["payment_id", "recovery_case_id", "job_id", "worker_id", "event_type"]:
            if hasattr(record, key):
                log_data[key] = getattr(record, key)
                
        if hasattr(record, "exc_info") and record.exc_info:
            exc_text = self.formatException(record.exc_info)
            log_data["exc_info"] = self._scrub_string(exc_text)
                
        return json.dumps(log_data)

def setup_logging():
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logger = logging.getLogger()
    logger.setLevel(level)
    
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        
    handler = logging.StreamHandler()
    
    if settings.LOG_FORMAT.lower() == "json":
        handler.setFormatter(JSONFormatter())
    else:
        # We must secure the text formatter fallback as well
        class ScrubbedTextFormatter(logging.Formatter):
            def _scrub(self, text: str) -> str:
                if not isinstance(text, str):
                    return text
                text = re.sub(r'Bearer\s+[a-zA-Z0-9_\-\.]+', 'Bearer [SCRUBBED]', text)
                text = re.sub(r'sk-[a-zA-Z0-9_\-\.]+', 'sk-[SCRUBBED]', text)
                return text
                
            def format(self, record):
                record.msg = self._scrub(str(record.msg))
                # Also scrub args if present, but since getMessage resolves them, 
                # we just override format and scrub the whole result
                formatted = super().format(record)
                return self._scrub(formatted)
                
        handler.setFormatter(ScrubbedTextFormatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        
    logger.addHandler(handler)
    logging.getLogger("httpx").setLevel(logging.WARNING)

def get_logger(name: str):
    return logging.getLogger(name)
