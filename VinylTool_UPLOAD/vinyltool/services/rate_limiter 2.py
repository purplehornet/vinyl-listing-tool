# vinyltool/services/rate_limiter.py
import time, threading
from collections import deque

class TokenBucket:
    def __init__(self, rate_per_sec=4, burst=8):
        self.capacity = burst
        self.tokens = burst
        self.rate = rate_per_sec
        self.updated = time.monotonic()
        self.lock = threading.Lock()

    def take(self, n=1):
        with self.lock:
            now = time.monotonic()
            delta = now - self.updated
            self.updated = now
            self.tokens = min(self.capacity, self.tokens + delta * self.rate)
            if self.tokens >= n:
                self.tokens -= n
                return True
            return False

    def wait(self, n=1):
        while not self.take(n):
            time.sleep(0.1)
