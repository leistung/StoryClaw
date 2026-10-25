"""Package-owned methods must work from any cwd and ship without application files."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from storyclaw.config.settings import StoryClawSettings
from storyclaw.skills.loader import list_skills, describe_skill

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
