"""Register an isolated Codex provider/profile while preserving the default GPT configuration."""
import copy
import json
from pathlib import Path
import shutil
import tomllib
from datetime import datetime

root = Path('C:/Users/daand/.codex')
config_path = root / 'config.toml'
original = config_path.read_text(encoding='utf-8-sig')
before = tomllib.loads(original)
if 'strata' in before.get('model_providers', {}):
    raise RuntimeError('An existing Strata provider needs review before changing it')
profile = root / 'qwen.config.toml'
catalog = root / 'model-catalogs/strata.json'
if profile.exists() or catalog.exists():
    raise RuntimeError('Strata profile/catalog already exists; refusing to overwrite')
models = json.loads((root / 'models_cache.json').read_text(encoding='utf-8'))['models']
model = copy.deepcopy(next(m for m in models if m['slug'] == 'gpt-5.5'))
model.update(slug='qwen3.8-flash-next-iq3_xxs', display_name='Qwen 3.8 Flash IQ3_XXS (Strata local)',
             description='Local model on this PC through Strata. Text only, 131,072-token context.',
             default_reasoning_level='medium',
             supported_reasoning_levels=[{'effort': e, 'description': e} for e in ('none','low','medium','high')],
             priority=1, upgrade=None, availability_nux=None, available_access_programs=None,
             additional_speed_tiers=[], service_tiers=[],
             context_window=131072, max_context_window=131072, effective_context_window_percent=90,
             input_modalities=['text'], supports_search_tool=False, supports_image_detail_original=False,
             web_search_tool_type='text', support_verbosity=False, use_responses_lite=False,
             include_skills_usage_instructions=False, include_plugin_usage_instructions=False,
             include_apps_usage_instructions=False, node_repl_disabled=True,
             comp_hash=None, tool_mode=None)
model.pop('model_messages', None)
model['base_instructions'] = ('You are a coding assistant running locally through Strata. '
                              'Help the user with their task. Use available tools when appropriate. '
                              'Follow repository instructions and report verified outcomes accurately.')
catalog.parent.mkdir(exist_ok=True)
catalog.write_text(json.dumps({'models':[model]}, ensure_ascii=False, indent=2), encoding='utf-8')
profile_text = '''# Explicitly selected local profile; the normal GPT configuration stays in config.toml.
model = "qwen3.8-flash-next-iq3_xxs"
model_provider = "strata"
model_context_window = 131072
model_auto_compact_token_limit = 110000
model_reasoning_effort = "medium"
model_reasoning_summary = "none"
model_catalog_json = "C:/Users/daand/.codex/model-catalogs/strata.json"
web_search = "disabled"
'''
profile.write_text(profile_text, encoding='utf-8')
addition = '''

# Strata is available only when explicitly selected, e.g. codex --profile qwen.
[model_providers.strata]
name = "Strata (local)"
base_url = "http://127.0.0.1:8080/v1"
wire_api = "responses"
requires_openai_auth = false
supports_websockets = false
stream_idle_timeout_ms = 600000
'''
new_text = original.rstrip() + addition
after = tomllib.loads(new_text)
preserved = copy.deepcopy(after)
preserved['model_providers'].pop('strata')
if not preserved['model_providers'] and 'model_providers' not in before:
    preserved.pop('model_providers')
assert preserved == before, 'Existing config changed'
backup = root / ('config.toml.before-strata-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.bak')
shutil.copy2(config_path, backup)
config_path.write_text(new_text, encoding='utf-8')
print(json.dumps({'default_model_unchanged':after.get('model'),
                  'default_provider_unchanged':after.get('model_provider','openai'),
                  'profile':str(profile),'catalog':str(catalog),'backup':str(backup)},indent=2))
