import logging
from logging.handlers import RotatingFileHandler
import os

def setup_logging(app, log_filename="server.log"):
    # Dynamically determine the project root directory (assumes this file is in 'app')
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    log_path = os.path.join(project_root, log_filename)
    
    # Console output for initial debugging of log setup
    print(f"Setting up logging to file: {log_path}")

    # Remove any pre-existing handlers to avoid duplicate log entries
    if app.logger.handlers:
        app.logger.handlers = []
    
    log_formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(module)s] %(message)s')
    
    # Configure rotating file handler for persistent log storage
    file_handler = RotatingFileHandler(log_path, maxBytes=1024*1024*5, backupCount=5) # 5MB per file, 5 backups
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(logging.INFO)

    # Always enable console handler for real-time debugging
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    console_handler.setLevel(logging.DEBUG)

    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)  # Console handler remains active for development
    app.logger.setLevel(logging.DEBUG) # Set to DEBUG for comprehensive output

    # Configure root logger to ensure all logs are captured and visible
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    # Remove all handlers from root logger to prevent duplicate log entries
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    # Attach both file and console handlers to the root logger
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Verify logging configuration
    app.logger.info(f"Logging configured. Log file at: {log_path}")
    
    return log_path
