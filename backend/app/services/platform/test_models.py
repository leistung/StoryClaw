"""Explicit local-test catalog setup; reuse encrypted GLM credentials without logging them."""
from copy import deepcopy
from sqlalchemy import select
from app.models import User
from .configs import load_models, load_pricing
from .platform import refresh_configs, save_config

TEST_MODELS = ('glm-4.5-air', 'glm-5.3-flash')

def catalog_for_tests(catalog):
    catalog = deepcopy(catalog)
    old = catalog.get('models', [])
    provider = next((m for m in old if 'open.bigmodel.cn' in m.get('base_url', '') and m.get('api_key_enc')), None)
    if provider is None:
        raise ValueError('先配置一个已加密保存 API 密钥的智谱模型')
    existing = {m['id']: m for m in old}
    entries = []
    for ident in TEST_MODELS:
        entry = deepcopy(existing.get(ident, provider))
        entry.update(id=ident, model=ident, display_name=ident.upper(), enabled=True,
                     thinking='disabled' if ident == TEST_MODELS[0] else 'enabled', fallback_models=['glm-5.3-flash'] if ident == TEST_MODELS[0] else [])
        entries.append(entry)
    # Preserve old entries and keys, but route new tests exclusively to requested models.
    for entry in old:
        if entry['id'] not in TEST_MODELS:
            entry.update(enabled=False, fallback_models=[])
            entries.append(entry)
    catalog['models'] = entries
    return catalog

async def configure_test_models(db):
    await refresh_configs(db)
    catalog = catalog_for_tests(load_models())
    pricing = load_pricing()
    # Platform test-credit rates, not a claim about supplier RMB prices.
    for ident in TEST_MODELS:
        pricing.setdefault('pricing', {}).setdefault(ident, {'input_price':0.3,'output_price':1.2,'enabled':True,'display_name':ident.upper()})
        pricing['pricing'][ident]['enabled'] = True
    actor = await db.scalar(select(User.id).where(User.is_admin.is_(True)).order_by(User.id).limit(1))
    if actor is None:
        raise ValueError('需要已存在的管理员账户')
    # Save pricing first so a concurrent request never sees a model without a price.
    await save_config(db, 'pricing.yaml', pricing, actor)
    await save_config(db, 'models.yaml', catalog, actor)
    return {'primary':TEST_MODELS[0], 'fallback':TEST_MODELS[1], 'credentials':'existing encrypted key reused'}
