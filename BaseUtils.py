import logging


def configure_logging():
    """Configure logging with enhanced format including function names"""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(funcName)s:%(lineno)d] - %(message)s'

    # Configure the root logger with the new format
    logging.basicConfig(
        format=log_format,
        level=logging.INFO,
        datefmt='%Y-%m-%d %H:%M:%S'
    )


# Call the configuration function here in Helper.py to ensure it's set up early
configure_logging()
