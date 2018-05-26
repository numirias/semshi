import functools
import logging
import os
import time


def lines_to_code(lines):
    return '\n'.join(lines)

def code_to_lines(code):
    return code.split('\n')


def debug_time(label_or_callable=None, detail=None):
    def inner(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            t = time.time()
            res = func(*args, **kwargs)
            label = label_or_callable
            if not isinstance(label, str):
                try:
                    label = func.__name__
                except AttributeError:
                    label = func.__class__.__name__
            text = 'TIME %s: %f ' % (label, time.time() - t)
            if detail is not None:
                if callable(detail):
                    text += detail(*args, **kwargs)
                else:
                    text += detail.format(*args, **kwargs)
            logger.debug(text)
            return res
        return wrapper
    if callable(label_or_callable):
        return inner(label_or_callable)
    return inner


def make_logger():
    logger = logging.getLogger('semshi')
    logger.setLevel(logging.ERROR)
    log_file = os.environ.get('SEMSHI_LOG_FILE')
    if log_file:
        handler = logging.FileHandler(log_file)
        logger.setLevel(os.environ.get('SEMSHI_LOG_LEVEL', logging.ERROR))
        logger.addHandler(handler)
    logger.debug('Semshi logger started.')
    return logger


logger = make_logger()
