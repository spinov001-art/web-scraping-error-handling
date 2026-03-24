# Web Scraping Error Handling — Production Patterns

Battle-tested error handling patterns from 77 production web scrapers.

**Stop losing data to transient failures.** These patterns handle timeouts, rate limits, connection drops, and server errors gracefully.

## Patterns Included

| Pattern | What It Solves | When to Use |
|---------|---------------|-------------|
| **Exponential Backoff** | Transient failures (503, timeouts) | Any HTTP request |
| **Circuit Breaker** | Cascading failures from dead services | Multiple targets |
| **Dead Letter Queue** | Lost URLs from failed scrapes | Batch processing |
| **Structured Logging** | "Why did my scraper stop?" at 3 AM | Production scrapers |
| **Resilient Scraper** | All of the above, combined | Real projects |

## Quick Start

```bash
pip install requests
python scraper_error_handling.py
```

## The 5 Patterns

### 1. Exponential Backoff with Jitter

```python
@retry_with_backoff(max_retries=3, base_delay=2.0)
def fetch_page(url):
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return r.text
```

Retries with increasing delays: 2s → 4s → 8s (with random jitter to avoid thundering herd).

### 2. Circuit Breaker

```python
cb = CircuitBreaker(failure_threshold=5, recovery_timeout=30)
result = cb.call(fetch_page, url)
```

After 5 failures → stops calling for 30 seconds → tests with one request → resumes if OK.

### 3. Dead Letter Queue

```python
dlq = DeadLetterQueue()
dlq.add(url, error="Timeout", attempts=1)
# Later: retry all failed URLs
successes, failures = dlq.retry_all(fetch_page)
```

### 4. All Combined: ResilientScraper

```python
scraper = ResilientScraper()
results = scraper.scrape_batch(["https://example.com/page1", "https://example.com/page2"])
print(scraper.report())
# {'success': 2, 'failed': 0, 'circuit_state': 'closed', 'dlq_size': 0}
```

## Common HTTP Errors and What They Mean

| Status | Meaning | Your Action |
|--------|---------|-------------|
| 429 | Rate limited | Read `Retry-After` header, wait, retry |
| 403 | Blocked/forbidden | Rotate User-Agent, check robots.txt |
| 503 | Server overloaded | Exponential backoff |
| 500 | Server error | Retry 2-3 times, then skip |
| 407 | Proxy auth required | Check proxy credentials |
| Timeout | Server too slow | Increase timeout or skip |
| ConnectionError | DNS/network issue | Check URL, retry once |

## Related Projects

- [Awesome Web Scraping 2026](https://github.com/Spinov001-art/awesome-web-scraping-2026) — 500+ scraping tools ⭐9
- [API Rate Limits Guide](https://github.com/Spinov001-art/api-rate-limits-guide) — Know limits before you hit them
- [API Authentication Guide](https://github.com/Spinov001-art/api-authentication-guide) — OAuth, API Keys, JWT
- [Python Data Pipelines](https://github.com/Spinov001-art/python-data-pipelines) — 15 pipeline templates
- [Free APIs List](https://github.com/Spinov001-art/free-apis-list) — 200+ APIs that need no key

## License

MIT
