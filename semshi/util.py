import functools
import logging
import time


logger = logging.getLogger('semshi')
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler('/tmp/semshi.log')
fh.setLevel(logging.DEBUG)
logger.addHandler(fh)


def debug_time(label_or_callable=None, detail=None):
    def inner(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            t = time.time()
            res = func(*args, **kwargs)
            label = label_or_callable
            if not isinstance(label, str):
                label = func.__name__
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
