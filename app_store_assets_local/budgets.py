"""Charge retained public bytes before accepting another bounded capture."""


class CaptureBudget:
    def __init__(self, limit):
        if type(limit) is not int or limit < 0:
            raise ValueError("invalid local captured byte bound")
        self.remaining = limit

    def take(self, data):
        if not isinstance(data, bytes) or len(data) > self.remaining:
            raise ValueError("local output exceeds total captured byte bound")
        self.remaining -= len(data)
        return data

    def read(self, path, capture, *, per_file=None):
        limit = self.remaining
        if per_file is not None:
            limit = min(limit, per_file)
        return self.take(capture(path, limit=limit))


def bounded_json(value, canonical, limit):
    data = canonical(value)
    if len(data) > limit:
        raise ValueError("local JSON exceeds the public reader byte bound")
    return data
