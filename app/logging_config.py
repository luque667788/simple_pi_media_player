import logging
from logging.handlers import RotatingFileHandler
import os

def setup_logging(app, log_filename="server.log"):
    # Determine project root dynamically (assuming logging_config.py is in 'app' directory)
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    log_path = os.path.join(project_root, log_filename)

    log_formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(module)s] %(message)s')
    
    # File Handler
    file_handler = RotatingFileHandler(log_path, maxBytes=1024*1024*5, backupCount=5) # 5MB per file, 5 backups
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(logging.INFO)

    # Console Handler (for development, can be commented out for production)
    # console_handler = logging.StreamHandler()
    # console_handler.setFormatter(log_formatter)
    # console_handler.setLevel(logging.DEBUG)

    if not app.logger.handlers: # Avoid adding handlers multiple times if setup is called again
        app.logger.addHandler(file_handler)
        # app.logger.addHandler(console_handler)
        app.logger.setLevel(logging.INFO)

    app.logger.info(f"Logging configured. Log file at: {log_path}")
