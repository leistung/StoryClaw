"""Dedicated durable consumers; API role may run independently without polling queues."""
import asyncio,argparse,time
from pathlib import Path
HEARTBEAT=Path('/tmp/storyclaw-worker-heartbeat')
async def pulse(tasks):
    while True:
        if any(task.done() for task in tasks):raise RuntimeError('A durable consumer stopped unexpectedly')
        HEARTBEAT.write_text(str(time.time()));await asyncio.sleep(10)
async def run():
    from .main import app,lifespan
    from .config import settings
    # Reuse exactly the API's dependency injection, with queue startup explicitly enabled.
    settings.workers_enabled=True
    async with lifespan(app):
        await pulse(app.state.worker_tasks)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--healthcheck',action='store_true');parser.add_argument('--migrate-originals',type=int,metavar='LIMIT');args=parser.parse_args()
    if args.healthcheck:
        raise SystemExit(0 if HEARTBEAT.exists() and time.time()-HEARTBEAT.stat().st_mtime<45 else 1)
    if args.migrate_originals is not None:
        from .services.blob_store import migrate_originals
        print('migrated_sources='+str(asyncio.run(migrate_originals(args.migrate_originals))));return
    asyncio.run(run())
if __name__=='__main__':main()
