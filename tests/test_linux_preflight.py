import json
import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('linux_preflight', Path(__file__).parents[1] / 'linux/preflight.py')
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)


def test_missing_secrets_block_service_without_exposing_values(tmp_path):
    problems = preflight.credential_problems(tmp_path, 'en', {'GROQ_API_KEY': 'your-groq-key-here'})
    assert any('GROQ_API_KEY' in p for p in problems)
    assert any('PEXELS_API_KEY' in p for p in problems)
    assert any('token.json' in p for p in problems)
    assert 'your-groq-key-here' not in ' '.join(problems)


def test_dutch_requires_its_own_refreshable_token(tmp_path):
    token = tmp_path / 'token.json'
    token.write_text(json.dumps({'refresh_token': 'private', 'client_id': 'private', 'client_secret': 'private'}))
    token.chmod(0o600)
    env = {'GROQ_API_KEY': 'private', 'PEXELS_API_KEY': 'private'}
    assert preflight.credential_problems(tmp_path, 'en', env) == []
    assert any('token_nl.json' in p for p in preflight.credential_problems(tmp_path, 'nl', env))


def test_invalid_or_world_readable_token_cannot_start(tmp_path):
    token = tmp_path / 'token.json'
    token.write_text('not json')
    token.chmod(0o644)
    problems = preflight.credential_problems(tmp_path, 'en', {'GROQ_API_KEY': 'private', 'PEXELS_API_KEY': 'private'})
    assert any('invalid JSON' in p for p in problems)
    assert any('owner-only' in p for p in problems)
