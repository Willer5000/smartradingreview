import ast
import os
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
APP = ROOT / 'app.py'
SCRIPT = ROOT / 'static' / 'script.js'


def _load_auth_helpers():
    source = APP.read_text(encoding='utf-8')
    tree = ast.parse(source)
    wanted = {'_auth_users', '_telegram_market_users'}
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    module = ast.Module(body=nodes, type_ignores=[])
    namespace = {'os': os}
    exec(compile(module, str(APP), 'exec'), namespace)
    return namespace['_auth_users'], namespace['_telegram_market_users']


class RC983DamirUserTests(unittest.TestCase):
    def test_damir_is_server_side_user_from_environment(self):
        auth_users, _ = _load_auth_helpers()
        env = {
            'SMARTRADING_PASSWORD_WILLER': 'w',
            'SMARTRADING_PASSWORD_DANILO': 'd',
            'SMARTRADING_PASSWORD_DAMIR': 'm',
        }
        with patch.dict(os.environ, env, clear=False):
            users = auth_users()
        self.assertEqual(users['Danilo'], 'd')
        self.assertEqual(users['Damir'], 'm')

    def test_password_is_not_hardcoded_in_repository(self):
        source = APP.read_text(encoding='utf-8')
        self.assertIn("SMARTRADING_PASSWORD_DAMIR", source)
        self.assertNotIn("'Damir': '1234'", source)
        self.assertNotIn('"Damir": "1234"', source)

    def test_default_market_access_matches_danilo(self):
        _, market_users = _load_auth_helpers()
        env = {
            'SMARTRADING_PASSWORD_WILLER': 'w',
            'SMARTRADING_PASSWORD_DANILO': 'd',
            'SMARTRADING_PASSWORD_DAMIR': 'm',
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(market_users('spot'), {'Willer', 'Danilo', 'Damir'})
            self.assertEqual(market_users('futures'), {'Willer', 'Danilo', 'Damir'})

    def test_explicit_danilo_market_permission_is_inherited_by_damir(self):
        _, market_users = _load_auth_helpers()
        env = {
            'SMARTRADING_PASSWORD_WILLER': 'w',
            'SMARTRADING_PASSWORD_DANILO': 'd',
            'SMARTRADING_PASSWORD_DAMIR': 'm',
            'SMARTRADING_SPOT_USERS': 'Danilo',
            'SMARTRADING_FUTURES_USERS': 'Willer,Danilo',
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(market_users('spot'), {'Danilo', 'Damir'})
            self.assertEqual(market_users('futures'), {'Willer', 'Danilo', 'Damir'})

    def test_damir_is_added_to_login_selector_without_template_replacement(self):
        script = SCRIPT.read_text(encoding='utf-8')
        self.assertIn("option.value === 'Damir'", script)
        self.assertIn("damirOption.value = 'Damir'", script)
        self.assertIn("loginUserSelect.appendChild(damirOption)", script)


if __name__ == '__main__':
    unittest.main()
