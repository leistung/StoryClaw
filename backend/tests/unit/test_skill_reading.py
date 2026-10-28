"""助手可渐进读取方法参考；不依赖数据库或付费模型。"""
import unittest
from types import SimpleNamespace
from storyclaw.orchestration.capabilities import get_capability
from storyclaw.skills.loader import read_skill_doc, read_skill_reference
from app.adapters.storyclaw.capabilities.materials import execute


class SkillReading(unittest.IsolatedAsyncioTestCase):
    async def test_existing_requests_read_the_main_document(self):
        arguments = get_capability('skills.read').schema.model_validate({'name':'chapter-craft'}).model_dump()
        result = await execute(SimpleNamespace(db=None, book=None), 'skills.read', arguments)
        self.assertEqual(result.data['reference'], '')
        self.assertEqual(result.data['document'], read_skill_doc('chapter-craft'))
        self.assertIn('references/revise.md', result.data['reference_files'])

    async def test_reference_read_is_explicit_and_preserves_method_identity(self):
        arguments = {'name':'modify-chapter', 'reference':'references/revise.md'}
        result = await execute(SimpleNamespace(db=None, book=None), 'skills.read', arguments)
        self.assertEqual(result.data['name'], 'chapter-craft')
        self.assertEqual(result.data['document'], read_skill_reference('chapter-craft', 'references/revise.md'))
        self.assertNotEqual(result.data['document'], read_skill_doc('chapter-craft'))

    async def test_undeclared_and_escaping_references_are_rejected(self):
        for reference in ('references/missing.md', 'references/../../loader.py', '/etc/passwd'):
            with self.subTest(reference=reference), self.assertRaises(ValueError):
                await execute(SimpleNamespace(db=None, book=None), 'skills.read', {'name':'chapter-craft', 'reference':reference})
