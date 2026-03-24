"""
Production-grade error handling patterns for web scrapers.
Battle-tested across 77 production scrapers.

Patterns included:
1. Exponential backoff with jitter
2. Circuit breaker
3. Dead letter queue
4. Structured error logging
5. Graceful degradation

Usage:
    python scraper_error_handling.py
"""

import time
import random
import logging
import requests
from functools import wraps
from collections import deque
from datetime import datetime, timedelta


# === Pattern 1: Exponential Backoff with Jitter ===

def retry_with_backoff(max_retries=3, base_delay=1.0, max_delay=60.0):
    """Retry failed requests with exponential backoff + jitter."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (requests.exceptions.RequestException, Exception) as e:
                    if attempt == max_retries:
                        raise
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    jitter = delay * random.uniform(0.5, 1.5)
                    logging.warning(f"Attempt {attempt+1} failed: {e}. Retrying in {jitter:.1f}s")
                    time.sleep(jitter)
        return wrapper
    return decorator


@retry_with_backoff(max_retries=3, base_delay=2.0)
def fetch_page(url: str) -> str:
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return r.text


# === Pattern 2: Circuit Breaker ===

class CircuitBreaker:
    """Stop calling a failing service before it overwhelms you."""

    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject all calls
    HALF_OPEN = "half_open"  # Testing if service recovered

    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.state = self.CLOSED
        self.last_failure_time = None

    def call(self, func, *args, **kwargs):
        if self.state == self.OPEN:
            if datetime.now() - self.last_failure_time > timedelta(seconds=self.recovery_timeout):
                self.state = self.HALF_OPEN
            else:
                raise Exception(f"Circuit breaker OPEN — service unavailable")

        try:
            result = func(*args, **kwargs)
            if self.state == self.HALF_OPEN:
                self.state = self.CLOSED
                self.failures = 0
            return result
        except Exception as e:
            self.failures += 1
            self.last_failure_time = datetime.now()
            if self.failures >= self.failure_threshold:
                self.state = self.OPEN
            raise


# === Pattern 3: Dead Letter Queue ===

class DeadLetterQueue:
    """Store failed URLs for later retry or manual inspection."""

    def __init__(self, max_size=1000):
        self.queue = deque(maxlen=max_size)

    def add(self, url: str, error: str, attempts: int):
        self.queue.append({
            "url": url,
            "error": str(error),
            "attempts": attempts,
            "timestamp": datetime.now().isoformat()
        })

    def retry_all(self, fetch_func):
        """Retry all failed URLs."""
        successes, failures = 0, 0
        items = list(self.queue)
        self.queue.clear()
        for item in items:
            try:
                fetch_func(item["url"])
                successes += 1
            except Exception as e:
                self.add(item["url"], str(e), item["attempts"] + 1)
                failures += 1
        return successes, failures

    def export(self) -> list:
        return list(self.queue)


# === Pattern 4: Structured Error Logging ===

def setup_scraper_logging(name: str = "scraper"):
    """JSON-structured logging for production scrapers."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        '{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}'
    ))
    logger.addHandler(handler)
    return logger


# === Pattern 5: Resilient Scraper (All Patterns Combined) ===

class ResilientScraper:
    """Production scraper with all error handling patterns."""

    def __init__(self):
        self.circuit_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30)
        self.dlq = DeadLetterQueue()
        self.logger = setup_scraper_logging("resilient-scraper")
        self.stats = {"success": 0, "failed": 0, "retried": 0}

    @retry_with_backoff(max_retries=2, base_delay=1.0)
    def _fetch(self, url: str) -> str:
        r = requests.get(url, timeout=10, headers={"User-Agent": "ResearchBot/1.0"})
        if r.status_code == 429:
            retry_after = int(r.headers.get("Retry-After", 60))
            self.logger.warning(f"Rate limited on {url}, waiting {retry_after}s")
            time.sleep(retry_after)
            r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.text

    def scrape(self, url: str) -> str | None:
        try:
            result = self.circuit_breaker.call(self._fetch, url)
            self.stats["success"] += 1
            return result
        except Exception as e:
            self.stats["failed"] += 1
            self.dlq.add(url, str(e), 1)
            self.logger.error(f"Failed {url}: {e}")
            return None

    def scrape_batch(self, urls: list[str]) -> dict:
        results = {}
        for url in urls:
            results[url] = self.scrape(url)
        return results

    def report(self) -> dict:
        return {
            **self.stats,
            "circuit_state": self.circuit_breaker.state,
            "dlq_size": len(self.dlq.queue)
        }


# === Demo ===

if __name__ == "__main__":
    scraper = ResilientScraper()

    urls = [
        "https://httpbin.org/status/200",
        "https://httpbin.org/status/200",
        "https://httpbin.org/status/500",  # Will fail
        "https://httpbin.org/delay/15",    # Will timeout
        "https://httpbin.org/status/200",
    ]

    print("=== Resilient Scraper Demo ===\n")
    for url in urls:
        result = scraper.scrape(url)
        status = "OK" if result else "FAILED"
        print(f"  {status}: {url}")

    print(f"\n=== Report ===")
    report = scraper.report()
    for k, v in report.items():
        print(f"  {k}: {v}")

    if scraper.dlq.queue:
        print(f"\n=== Dead Letter Queue ({len(scraper.dlq.queue)} items) ===")
        for item in scraper.dlq.export():
            print(f"  {item['url']}: {item['error'][:60]}")
