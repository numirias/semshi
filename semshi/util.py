import logging
import time


logger = logging.getLogger('semshi')
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler('/tmp/semshi.log')
fh.setLevel(logging.DEBUG)
logger.addHandler(fh)


def debug_time(label=None, detail=None):
    def inner(func):
        def wrapper(*args, **kwargs):
            t = time.time()
            res = func(*args, **kwargs)
            nonlocal label
            if label is None:
                label = str(func)
            text = 'TIME %s: %f ' % (label, time.time() - t)
            if detail is not None:
                if callable(detail):
                    text += detail(*args, **kwargs)
                else:
                    text += detail.format(*args, **kwargs)
            logger.debug(text)
            return res
        return wrapper
    return inner
