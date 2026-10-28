"""Per-process execution capacity; independent of database and job implementations."""
import os
import math
from pathlib import Path
from app.config import settings

def worker_slots():
    """Startup capacity estimate, configurable per replica; never promises provider quota."""
    if settings.worker_job_concurrency != 'auto':
        return int(settings.worker_job_concurrency)
    cpus = os.cpu_count() or 1
    try:
        cpus = min(cpus, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        pass
    try:
        quota, period = Path('/sys/fs/cgroup/cpu.max').read_text().split()
        if quota != 'max':
            cpus = min(cpus, max(1, math.ceil(int(quota) / int(period))))
    except (OSError, ValueError, ZeroDivisionError):
        pass
    memory = None
    try:
        memory = os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE')
    except (ValueError, OSError, AttributeError):
        pass
    try:
        limit = Path('/sys/fs/cgroup/memory.max').read_text().strip()
        if limit != 'max':
            memory = min(memory, int(limit)) if memory else int(limit)
    except (OSError, ValueError):
        pass
    # I/O-heavy jobs: 4 slots/visible CPU, reserving 256MiB/slot from half of memory.
    slots = max(1, cpus * 4)
    if memory:
        slots = min(slots, max(1, memory // (512 * 1024 * 1024)))
    return slots


