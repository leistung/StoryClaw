"""Explicitly promote an existing registered account. Never creates default passwords."""
import argparse
import asyncio
from sqlalchemy import select
from .database import AsyncSessionLocal, engine
from .models import User
from .models.platform import PlatformEvent

async def promote(username, password=None):
    try:
        async with AsyncSessionLocal() as db:
            user = await db.scalar(select(User).where(User.username == username).with_for_update())
            if not user:
                if password is None:
                    raise SystemExit('用户不存在，请先注册，或使用 --create 创建账号')
                from .core.security import hash_password
                if not 6 <= len(password) or len(password.encode('utf-8')) > 72:
                    raise SystemExit('密码至少 6 字符且不超过 72 字节')
                user = User(username=username, password_hash=hash_password(password), version='business', credits_balance=10000)
                db.add(user)
                await db.flush()
                from .models import CreditsLedger
                db.add(CreditsLedger(user_id=user.id, delta=10000, reason='开发管理员初始积分', model='admin'))
            elif password is not None:
                raise SystemExit('账号已存在；不会覆盖密码，请选择新用户名或只提升权限')
            user.is_admin = True
            db.add(PlatformEvent(kind='audit', actor_id=user.id, action='admin.bootstrap', target=str(user.id), details={}))
            await db.commit()
            print(f'已将 {username} 设置为管理员，请重新登录')
    finally:
        await engine.dispose()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='将现有注册用户设置为平台管理员')
    parser.add_argument('username')
    parser.add_argument('--create', action='store_true', help='创建新管理员，初始 10000 开发积分')
    parser.add_argument('--password-stdin', action='store_true', help='从标准输入读取新账号密码')
    args = parser.parse_args()
    password = None
    if args.create:
        if args.password_stdin:
            import sys
            password = sys.stdin.readline().rstrip('\n')
        else:
            import getpass
            password = getpass.getpass('新管理员密码: ')
    asyncio.run(promote(args.username, password))
