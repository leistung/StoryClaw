"""设定与 Skill 查询、版本绑定的修改候选。公共权限边界由 Ports 统一校验。"""
from sqlalchemy import select
from storyclaw.contracts import CapabilityResult

async def execute(ctx, name, arguments):
    db = ctx.db
    book = ctx.book
    if name in ('skills.list', 'skills.read'):
        from storyclaw.skills.loader import list_skills, describe_skill, read_skill_doc, read_skill_reference
        if name == 'skills.list':
            return CapabilityResult(content='可用创作方法', data={'skills': list_skills()})
        meta = describe_skill(arguments['name'])
        if not meta.get('available'):
            raise ValueError('该创作方法不存在或已停用')
        reference = arguments.get('reference', '')
        # 仅暴露清单登记的静态方法材料；路径约束仍由资源加载器二次校验。
        if reference and reference not in meta['reference_files']:
            raise ValueError('参考文件未登记，请从 reference_files 中选择')
        document = read_skill_reference(arguments['name'], reference) if reference else read_skill_doc(arguments['name'])
        if not document:
            raise ValueError('创作方法文件不可读取')
        return CapabilityResult(content='创作参考已读取' if reference else '创作方法已读取', data={**meta, 'reference': reference, 'document': document})
    if name in ('setting.read', 'setting.update'):
        from app.models import ConfigEntity
        from app.services.agent.setting_edits import setting_data, setting_hash
        query = select(ConfigEntity).where(ConfigEntity.book_id == book.id, ConfigEntity.entity_type.in_(['character', 'world', 'scene', 'item', 'plot']), ConfigEntity.category != 'chapter-plan')
        if name == 'setting.read':
            if arguments['entity_type']:
                query = query.where(ConfigEntity.entity_type == arguments['entity_type'])
            if arguments['keyword']:
                query = query.where(ConfigEntity.name.contains(arguments['keyword'], autoescape=True))
            rows = list(await db.scalars(query.order_by(ConfigEntity.id).limit(30)))
            return CapabilityResult(content='已读取本作品设定档案', data={'settings': [{**setting_data(r), 'content_hash': setting_hash(r)} for r in rows], 'limit': 30})
        entity = await db.scalar(query.where(ConfigEntity.id == arguments['entity_id']))
        if not entity:
            raise ValueError('本作品的设定档案不存在')
        if setting_hash(entity) != arguments['expected_hash']:
            raise ValueError('设定已变化，请重新读取后再提出修改')
        before = setting_data(entity)
        after = {**before, **{k: arguments[k] for k in ('name', 'category', 'description') if arguments[k] is not None}}
        return CapabilityResult(content=f'### {after['name']} · 设定修改候选\n\n{after['description']}', data={'artifact': True, 'kind': 'setting.update', 'adopted': False, 'entity_id': entity.id, 'base_hash': setting_hash(entity), 'setting_change': {'before': before, 'after': after}})
