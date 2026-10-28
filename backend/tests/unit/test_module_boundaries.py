"""防止目录整理后重新出现跨层反向依赖或遗漏能力执行器。"""
import ast
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / 'app'


def imports(path):
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom):
            yield node.module or ''
        elif isinstance(node, ast.Import):
            yield from (name.name for name in node.names)


class ModuleBoundaries(unittest.TestCase):
    def test_services_do_not_depend_on_http_routes(self):
        for path in (APP / 'services').rglob('*.py'):
            for name in imports(path):
                self.assertFalse(name.startswith('app.gateway'), f'{path}: {name}')

    def test_contracts_do_not_depend_on_persistence_or_execution(self):
        for path in (APP / 'schemas').glob('*.py'):
            for name in imports(path):
                self.assertFalse(name.startswith(('sqlalchemy', 'fastapi', 'app.models',
                                                 'app.services', 'app.gateway')), f'{path}: {name}')

    def test_every_model_capability_has_an_execution_handler(self):
        from storyclaw.orchestration.capabilities import CATALOG
        from app.adapters.storyclaw.capabilities import HANDLERS, handler_for
        self.assertFalse(set(HANDLERS) - set(CATALOG), '已移除的能力不能残留路由')
        for name in CATALOG:
            with self.subTest(name=name):
                self.assertTrue(callable(handler_for(name)))
        with self.assertRaises(ValueError):
            handler_for('not.a.real.capability')
