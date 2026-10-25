"""Private S3/MinIO objects with AWS SigV4. No public URLs or browser-held keys."""
import hashlib,hmac,re
from datetime import datetime,timezone
from urllib.parse import urlsplit,quote
import httpx
from fastapi import HTTPException
from app.config import settings
class S3Store:
    def __init__(self,endpoint,bucket,access_key,secret_key,region='us-east-1',transport=None):
        parsed=urlsplit(endpoint)
        if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.query or parsed.path not in ('','/') or parsed.username:raise ValueError('Invalid S3 endpoint')
        if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]',bucket):raise ValueError('Invalid private bucket name')
        if not access_key or not secret_key:raise ValueError('S3 credentials are required')
        self.endpoint=endpoint.rstrip('/');self.host=parsed.netloc;self.bucket=bucket;self.access=access_key;self.secret=secret_key;self.region=region;self.transport=transport
    async def request(self,method,key='',data=b''):
        path='/'+self.bucket+('/'+quote(key,safe='/~') if key else '')
        date=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');day=date[:8];digest=hashlib.sha256(data).hexdigest()
        headers={'host':self.host,'x-amz-content-sha256':digest,'x-amz-date':date}
        signed=';'.join(sorted(headers));canonical=''.join(k+':'+headers[k]+'\n' for k in sorted(headers))
        request='\n'.join([method,path,'',canonical,signed,digest]);scope=f'{day}/{self.region}/s3/aws4_request'
        to_sign='AWS4-HMAC-SHA256\n'+date+'\n'+scope+'\n'+hashlib.sha256(request.encode()).hexdigest()
        key_bytes=('AWS4'+self.secret).encode()
        for part in (day,self.region,'s3','aws4_request'):key_bytes=hmac.new(key_bytes,part.encode(),hashlib.sha256).digest()
        signature=hmac.new(key_bytes,to_sign.encode(),hashlib.sha256).hexdigest()
        headers['Authorization']=f'AWS4-HMAC-SHA256 Credential={self.access}/{scope}, SignedHeaders={signed}, Signature={signature}'
        async with httpx.AsyncClient(timeout=60,transport=self.transport,follow_redirects=False) as client:
            return await client.request(method,self.endpoint+path,headers=headers,content=data)
    async def ensure_bucket(self):
        response=await self.request('HEAD')
        if response.status_code==404:
            response=await self.request('PUT')
            if response.status_code in (200,204,409):return
        elif response.is_success:return
        raise HTTPException(503,'私有稿件存储不可用，请检查S3/MinIO配置')
    async def put(self,key,data):
        await self.ensure_bucket();r=await self.request('PUT',key,data)
        if not r.is_success:raise HTTPException(503,'原稿保存失败，未采用此次上传')
    async def get(self,key):
        r=await self.request('GET',key)
        if not r.is_success:raise HTTPException(503,'原稿对象暂不可读取，请联系运营核对，不会返回空文件')
        return r.content
    async def delete(self,key):
        r=await self.request('DELETE',key)
        if not r.is_success and r.status_code!=404:raise HTTPException(503,'私有对象清理未完成')
def store():
    return S3Store(settings.source_s3_endpoint,settings.source_s3_bucket,settings.source_s3_access_key,settings.source_s3_secret_key,settings.source_s3_region)
async def write_original(db,source,data):
    if settings.source_storage_backend=='database':return
    from app.models.operations import SourceBlob
    key=f'originals/{source.user_id}/{source.id}/{source.file_hash}'
    from app.database import AsyncSessionLocal
    from app.services.storage.cleanup import enqueue
    async with AsyncSessionLocal() as outbox:
        await enqueue(outbox,'blob',{'key':key},24);await outbox.commit()
    service=store();await service.put(key,data)
    # Read-back verifies a genuinely durable byte-identical original before dropping SQL bytes.
    if hashlib.sha256(await service.get(key)).hexdigest()!=source.file_hash:raise HTTPException(503,'原稿存储校验失败，未删除数据库副本')
    db.add(SourceBlob(source_id=source.id,object_key=key,digest=source.file_hash,size=len(data)));source.original=b''
async def read_original(db,source):
    from app.models.operations import SourceBlob
    blob=await db.get(SourceBlob,source.id)
    data=await store().get(blob.object_key) if blob else source.original
    if not data or hashlib.sha256(data).hexdigest()!=source.file_hash:raise HTTPException(503,'原稿完整性校验失败，请联系运营恢复副本')
    return data
async def migrate_originals(limit=50):
    from app.database import AsyncSessionLocal
    from app.models.studio import StorySource
    from app.models.operations import SourceBlob
    from sqlalchemy import select
    if settings.source_storage_backend!='s3':raise ValueError('Select SOURCE_STORAGE_BACKEND=s3 before migration')
    moved=0
    # One committed source at a time: interruption cannot erase the only copy.
    for _ in range(limit):
        async with AsyncSessionLocal() as db:
            row=await db.scalar(select(StorySource).where(~StorySource.id.in_(select(SourceBlob.source_id))).order_by(StorySource.created_at).with_for_update(skip_locked=True).limit(1))
            if not row:break
            await write_original(db,row,row.original);await db.commit();moved+=1
    return moved
