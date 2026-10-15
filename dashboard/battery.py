"""Smoothing for the S9's max77705 fuel gauge: capacity dips under load, so report the median of the last 60 s."""
import statistics
import time
from collections import deque

PCT = deque()  # (monotonic s, %)


def smooth_pct(p, now=None, window=60):
    now = time.monotonic() if now is None else now
    PCT.append((now, p))
    while PCT[0][0] < now - window:
        PCT.popleft()
    return round(statistics.median(x for _, x in PCT))


if __name__ == '__main__':
    assert [smooth_pct(p, now=t) for t, p in enumerate([44, 44, 28, 44, 40])][-1] == 44  # dips don't move it
    assert smooth_pct(30, now=100) == 30  # old samples age out
    print('ok')
