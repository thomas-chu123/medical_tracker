import logging
import sys
from pathlib import Path

# Log format
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FILE = Path(__file__).parent.parent.parent / "server.log"

def setup_logger(name: str) -> logging.Logger:
    """Create and configure a logger that writes to console and server.log."""
    logger = logging.getLogger(name)
    
    # Only configure if not already configured to avoid duplicate handlers
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        formatter = logging.Formatter(LOG_FORMAT)
        
        # Console Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # File Handler
        try:
            file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            print(f"Failed to setup file handler for logging: {e}")
            
    return logger

# Global logger instance for convenience
logger = setup_logger("medical_app")
