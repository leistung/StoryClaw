"""Explicit local operations. No model calls, destructive database resets or key output."""
import argparse,asyncio,json
async def activity():
    from sqlalchemy import select,func
    from app.database import AsyncSessionLocal
    from app.models.product import WorkJob
    from app.models.agent import AgentRun
    from app.models.studio import StudioTask
    async with AsyncSessionLocal() as db:
        counts={}
        for name,model,states in [('jobs',WorkJob,['queued','running']),('runs',AgentRun,['accepted','running']),('plans',StudioTask,['queued','running'])]:
            counts[name]=await db.scalar(select(func.count()).select_from(model).where(model.status.in_(states)))
    print(json.dumps(counts));return 2 if any(counts.values()) else 0
async def storage_check():
    from uuid import uuid4
    import hashlib,httpx
    from app.services.storage.blob_store import store
    service=store();key='acceptance/'+str(uuid4());data=b'StoryClaw private storage acceptance fixture'
    try:
        await service.put(key,data)
        if await service.get(key)!=data:raise RuntimeError('Object round-trip mismatch')
        async with httpx.AsyncClient(timeout=10) as client:response=await client.get(service.endpoint+'/'+service.bucket+'/'+key)
        if response.status_code not in (401,403):raise RuntimeError('Bucket is publicly readable or access policy cannot be verified')
        print(json.dumps({'roundtrip':True,'anonymous_read_denied':True,'sha256':hashlib.sha256(data).hexdigest()}))
    finally:await service.delete(key)
    return 0
async def index_check():
    from uuid import uuid4
    from storyclaw.rag import service as rag
    from storyclaw.rag.embedding import _hash_vector
    from storyclaw.config.settings import settings as agent_settings
    from pymilvus import utility
    namespace='acceptance_'+uuid4().hex;pid=-123456789;uid=0
    name=rag._milvus._collection_name(uid,namespace)
    try:
        vector=_hash_vector('Operational acceptance fixture only',agent_settings.milvus_dim)
        count=rag._milvus.upsert(uid,namespace,[{'id':pid*10000,'chapter_id':pid,'volume_id':0,'chunk_idx':0,'text':'Operational acceptance fixture only','embedding':vector}])
        if count!=1:raise RuntimeError('Vector write failed')
        ents,_=rag._neo4j.upsert_chapter(uid,namespace,pid,[{'name':'AcceptanceFixture','type':'item','description':'Temporary test data'}],[])
        if ents!=1:raise RuntimeError('Graph write failed')
        await rag.delete_generation(uid,namespace,pid)
        if rag._milvus.count_chunks(uid,namespace,pid)!=0 or rag._neo4j.entity_count(uid,namespace,pid)!=0:raise RuntimeError('Physical cleanup did not finish')
        print(json.dumps({'vector_write':True,'graph_write':True,'physical_cleanup':True,'model_calls':0}))
    finally:
        if rag._milvus.connect() and utility.has_collection(name):utility.drop_collection(name)
        if rag._neo4j.connect():
            with rag._neo4j._driver.session() as session:
                session.run('MATCH (e:StoryEntity {user_id:$uid,book_id:$bid}) DETACH DELETE e',uid=uid,bid=namespace).consume()
                session.run('MATCH (c:Chapter {book_id:$bid}) DETACH DELETE c',bid=namespace).consume()
                session.run('MATCH (b:Book {user_id:$uid,book_id:$bid}) DETACH DELETE b',uid=uid,bid=namespace).consume()
    return 0
async def model_check(model_id=None):
    """Bounded live inference probe: max 5 platform credits, one text and one embedding request."""
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models import User
    from app.main import app
    from app.main import lifespan
    from app.config import settings
    from app.services.platform.metering import usage_scope
    from app.services.platform.metering import price
    from app.services.platform.llm import build_llm_from_choice
    from storyclaw.workflows.acceptance import model_probe
    settings.workers_enabled=False
    report={'budget':5,'text':False,'embedding':False};meter=None
    async with lifespan(app):
        async with AsyncSessionLocal() as db:
            uid=await db.scalar(select(User.id).where(User.is_admin==True).order_by(User.id).limit(1))
        if uid is None:raise RuntimeError('An administrator account is required')
        async with usage_scope(uid) as meter:
            reserve=meter.reserve
            async def bounded(model,ins,outs):
                if meter.spent+price(model,ins,outs)>5:raise ValueError('Acceptance budget exhausted before supplier call')
                return await reserve(model,ins,outs)
            meter.reserve=bounded
            client,model=await build_llm_from_choice({'kind':'business', **({'model_id':model_id} if model_id else {})})
            report.update(await model_probe(client,model,meter))
            report['credits_cost']=meter.spent;report['calls']=meter.calls
    print(json.dumps(report,ensure_ascii=False));return 0 if report['text'] and report['embedding'] else 1
def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['activity','storage-check','index-check','model-check','migrate-originals','configure-test-models']);parser.add_argument('--limit',type=int,default=50);parser.add_argument('--model');args=parser.parse_args()
    if args.action=='configure-test-models':
        async def configure():
            from app.database import AsyncSessionLocal
            from app.services.platform.test_models import configure_test_models
            async with AsyncSessionLocal() as db:
                return await configure_test_models(db)
        print(json.dumps(asyncio.run(configure())));return
    if args.action=='activity':raise SystemExit(asyncio.run(activity()))
    if args.action=='storage-check':raise SystemExit(asyncio.run(storage_check()))
    if args.action=='index-check':raise SystemExit(asyncio.run(index_check()))
    if args.action=='model-check':raise SystemExit(asyncio.run(model_check(args.model)))
    from app.services.storage.blob_store import migrate_originals
    print('migrated_sources='+str(asyncio.run(migrate_originals(args.limit))))
if __name__=='__main__':main()
