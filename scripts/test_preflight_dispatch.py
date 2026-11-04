#!/usr/bin/env python3
"""Regression checks for availability versus CLI capability and runtime binding."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import preflight_dispatch as preflight
from test_profile_fixtures import write_profiles


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root / 'home'
        write_profiles(self.home)
        self.role = 'delegated_researcher'
        self.profile = self.home / 'agents' / (self.role + '.toml')
        self.cli = self.root / 'codex-fixture'
        self.cli.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
if '--version' in sys.argv:
 print('fixture-cli 1.0');sys.exit()
if '--help' in sys.argv:
 print('--model --config --sandbox --json --cd --skip-git-repo-check');sys.exit()
if os.environ.get('PROBE_TEST_TIMEOUT'):
 import time;time.sleep(15)
sys.stdin.read()
thread='aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
print(json.dumps({'type':'thread.started','thread_id':thread}))
model=sys.argv[sys.argv.index('--model')+1]
sandbox=sys.argv[sys.argv.index('--sandbox')+1]
provider='-c' in sys.argv and 'model_provider="fixture-provider"' in sys.argv
if os.environ.get('PROBE_TEST_ERROR'):
 print(json.dumps({'type':'error','message':os.environ['PROBE_TEST_ERROR']}));sys.exit(1)
path=Path(os.environ['CODEX_HOME'])/'sessions/2026/10/17'/('rollout-'+thread+'.jsonl')
path.parent.mkdir(parents=True,exist_ok=True)
if not os.environ.get('PROBE_TEST_NO_METADATA'):
 path.write_text(json.dumps({'type':'turn_context','payload':{'model':model,'effort':'medium',
 'sandbox_policy':{'type':os.environ.get('PROBE_TEST_SANDBOX',sandbox)}}})+'\\n')
print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'DELEGATION_PROBE_OK'}}))
print(json.dumps({'type':'turn.completed'}))
''')
        self.cli.chmod(0o755)

    def tearDown(self):
        self.temp.cleanup()

    def run_probe(self, **env):
        result, argv = preflight.prepare(self.home, self.role, str(self.cli))
        with patch.dict(os.environ, env):
            return preflight.probe(self.home, result, argv, self.root / 'evidence', 1)

    def test_static_check_never_claims_available(self):
        result, argv = preflight.prepare(self.home, self.role, str(self.cli))
        self.assertFalse(result['dispatchable'])
        self.assertEqual(result['status'], 'probe_required')
        self.assertEqual(argv[argv.index('--model')+1], 'gpt-6.1-sol')
        self.assertEqual(argv[argv.index('--sandbox')+1], 'read-only')

    def test_completed_probe_requires_matching_runtime(self):
        result = self.run_probe()
        self.assertTrue(result['dispatchable'])
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(result['observed_binding']['sandbox_mode'], 'read-only')

    def test_runtime_permission_mismatch_blocks(self):
        result = self.run_probe(PROBE_TEST_SANDBOX='workspace-write')
        self.assertTrue(result['probe_completed'])
        self.assertFalse(result['dispatchable'])
        self.assertEqual(result['status'], 'runtime_binding_unverified')

    def test_computer_role_model_probe_does_not_prove_ui_capability(self):
        self.role = 'delegated_computer_worker'
        result = self.run_probe()
        self.assertTrue(result['probe_completed'])
        self.assertEqual(result['observed_binding']['model'], 'gpt-6.1-terra')
        self.assertFalse(result['dispatchable'])
        self.assertEqual(result['status'], 'capability_probe_required')

    def test_missing_metadata_is_not_success(self):
        result = self.run_probe(PROBE_TEST_NO_METADATA='1')
        self.assertFalse(result['dispatchable'])
        self.assertEqual(result['status'], 'runtime_binding_unverified')

    def test_account_model_rejection_is_not_cli_flag_rejection(self):
        result = self.run_probe(PROBE_TEST_ERROR="The 'gpt-6.1-sol' model is not supported when using Codex with a ChatGPT account.")
        self.assertEqual(result['status'], 'model_unavailable')
        self.assertFalse(result['dispatchable'])
        self.assertEqual(result['model'], 'gpt-6.1-sol')

    def test_timeout_stops_probe(self):
        result = self.run_probe(PROBE_TEST_TIMEOUT='1')
        self.assertEqual(result['status'], 'timeout')
        self.assertFalse(result['dispatchable'])

    def test_error_categories_remain_distinct(self):
        for text, expected in [
            ('error: unexpected argument --model', 'cli_argument_unsupported'),
            ('401 Unauthorized', 'authentication_failed'),
            ('429 rate limit exceeded', 'rate_limited'),
            ("reasoning effort high is not supported with this model", 'effort_unavailable'),
            ('error sending request', 'network_failed'),
            ('error loading config', 'configuration_failed'),
            ('tool ground_docs handshake failed', 'execution_failed'),
        ]:
            with self.subTest(text=text):
                self.assertEqual(preflight.classify_failure(text)[0], expected)

    def test_provider_override_is_preserved_without_substitution(self):
        self.profile.write_text(self.profile.read_text()+'model_provider = "fixture-provider"\n')
        result, argv = preflight.prepare(self.home, self.role, str(self.cli))
        self.assertEqual(result['provider'], 'fixture-provider')
        self.assertIn('model_provider="fixture-provider"', argv)

    def test_explicit_provider_needs_matching_runtime_evidence(self):
        self.profile.write_text(self.profile.read_text()+'model_provider = "fixture-provider"\n')
        result = self.run_probe()
        self.assertTrue(result['probe_completed'])
        self.assertFalse(result['dispatchable'])
        self.assertEqual(result['status'], 'runtime_binding_unverified')

    def test_unhandled_profile_configuration_fails_closed(self):
        self.profile.write_text(self.profile.read_text()+'[model_providers.private]\nname="private"\n')
        with self.assertRaisesRegex(SystemExit, 'cannot apply full binding'):
            preflight.prepare(self.home, self.role, str(self.cli))

    def test_never_overwrites_existing_evidence(self):
        target = self.root / 'evidence'
        target.mkdir()
        result, argv = preflight.prepare(self.home, self.role, str(self.cli))
        with self.assertRaises(FileExistsError):
            preflight.probe(self.home, result, argv, target, 1)

    def test_cli_missing_flags_fails_before_model_request(self):
        with patch('preflight_dispatch.subprocess.run', return_value=subprocess.CompletedProcess([],0,'--version only','')):
            with self.assertRaisesRegex(SystemExit, 'lacks required flags'):
                preflight.prepare(self.home, self.role, str(self.cli))

    def test_binding_fingerprint_changes_with_auth_or_configuration(self):
        before, _ = preflight.prepare(self.home, self.role, str(self.cli))
        (self.home/'auth.json').write_text('{"fixture":"no-secret"}')
        after, _ = preflight.prepare(self.home, self.role, str(self.cli))
        self.assertNotEqual(before['binding_fingerprint'], after['binding_fingerprint'])


if __name__ == '__main__':
    unittest.main()
