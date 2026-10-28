"""Package-owned methods must work from any cwd and ship without application files."""
import os
import json
import re
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from storyclaw.config.settings import StoryClawSettings
from storyclaw.skills.loader import list_skills, describe_skill, method_instructions, read_skill_reference

class MethodResources(unittest.TestCase):
    def test_builtin_resources_are_independent_of_working_directory(self):
        previous=Path.cwd()
        try:
            with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'SKILLS_DIR':''}):
                os.chdir(folder)
                settings=StoryClawSettings()
                self.assertEqual(len(list_skills(settings.skills_path)),11)
                self.assertEqual(settings.skills_path.name,'resources')
        finally:
            os.chdir(previous)

    def test_explicit_method_directory_can_override_builtin(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'SKILLS_DIR':folder}):
            self.assertEqual(StoryClawSettings().skills_dir,folder)

    def test_builtin_alias_keeps_method_identity(self):
        self.assertEqual(describe_skill('write-chapter')['content_hash'],describe_skill('chapter-craft')['content_hash'])

    def test_every_reference_is_discoverable_and_shipped_in_the_manifest(self):
        from storyclaw.orchestration.capabilities import CATALOG
        base = Path(__file__).resolve().parents[1] / 'storyclaw/skills/resources'
        for folder in sorted(base.iterdir()):
            with self.subTest(skill=folder.name):
                manifest = json.loads((folder / 'manifest.json').read_text())
                declared = set(manifest['reference_files'])
                actual = {p.relative_to(folder).as_posix() for p in (folder / 'references').glob('*.md')}
                self.assertEqual(declared, actual, '未登记的材料无法被助手发现')
                for cap in manifest['compatible_capabilities']:
                    self.assertIn(cap, CATALOG)
                linked = set(re.findall(r'\]\((references/[^)]+\.md)\)', (folder / 'SKILL.md').read_text()))
                self.assertEqual(linked, declared)
                for references in manifest['instruction_references'].values():
                    self.assertLessEqual(len(references), 2, '内置任务仅预载相关参考，其余按需读取')
                    self.assertTrue(set(references) <= declared)
                with patch('storyclaw.skills.loader.settings.skills_dir', str(base)):
                    for relative in declared:
                        self.assertTrue(read_skill_reference(folder.name, relative))
                    self.assertTrue(method_instructions(folder.name))

    def test_task_routes_include_contracts_without_loading_other_modes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'chapter-craft'
            (root / 'references').mkdir(parents=True)
            (root / 'SKILL.md').write_text('## Parameters\ninput-marker\n## Method\nmethod-marker\n## Constraints\nboundary-marker\n## Output\noutput-marker\n')
            for name in ('write', 'revise'):
                (root / f'references/{name}.md').write_text(f'{name}-marker')
            manifest = {'reference_files':['references/write.md', 'references/revise.md'],
                        'instruction_references':{'default':['references/write.md'],
                                                  'modify-chapter':['references/revise.md']}}
            (root / 'manifest.json').write_text(json.dumps(manifest))
            with patch('storyclaw.skills.loader.settings.skills_dir', folder):
                revised = method_instructions('modify-chapter')
                self.assertIn('revise-marker', revised)
                self.assertNotIn('write-marker', revised)
                for marker in ('input-marker', 'method-marker', 'boundary-marker', 'output-marker'):
                    self.assertIn(marker, revised)
                self.assertIn('write-marker', method_instructions('write-chapter'))
                # 旧自定义资源没有路由字段时仍按原有别名选择参考。
                del manifest['instruction_references']
                (root / 'manifest.json').write_text(json.dumps(manifest))
                self.assertIn('revise-marker', method_instructions('modify-chapter'))

    def test_reference_changes_invalidate_version_hash_and_cannot_escape_root(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'chapter-craft'
            (root / 'references').mkdir(parents=True)
            (root / 'SKILL.md').write_text('## Method\nmethod\n')
            reference = root / 'references/write.md'
            reference.write_text('original')
            secret = Path(folder) / 'outside.md'
            secret.write_text('outside')
            (root / 'references/link.md').symlink_to(secret)
            with patch('storyclaw.skills.loader.settings.skills_dir', folder):
                before = describe_skill('chapter-craft')['content_hash']
                reference.write_text('updated')
                after = describe_skill('write-chapter')['content_hash']
                self.assertNotEqual(before, after)
                self.assertEqual(read_skill_reference('chapter-craft', 'references/write.md'), 'updated')
                self.assertEqual(read_skill_reference('chapter-craft', 'references/../../outside.md'), '')
                self.assertEqual(read_skill_reference('chapter-craft', 'references/link.md'), '')
