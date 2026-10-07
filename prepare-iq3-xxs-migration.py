"""Prepare a standalone verified downloader and an explicit deletion proposal. Does not delete or download weights."""
import json
from pathlib import Path
from datetime import datetime, timezone

root = Path('E:/Strata')
data = Path('E:/Strata-data')
source = (root / 'download-iq3_s-parallel.py').read_text(encoding='utf-8')
new_source = source.replace('IQ3_S', 'IQ3_XXS').replace('iq3_s', 'iq3_xxs')
(root / 'download-iq3_xxs-parallel.py').write_text(new_source, encoding='utf-8')
directories = [data / 'models/IQ3_S', data / 'packs/iq3_s']
files = [p for p in root.iterdir() if p.is_file() and (
    'iq3_s' in p.name.lower() or p.name in ('increase-qwen-context.py', 'CONTINUAR-MANANA.bat'))]
plan = {
    'state': 'awaiting_confirmation',
    'created_at': datetime.now(timezone.utc).isoformat(),
    'source_model': 'IQ3_S', 'target_model': 'IQ3_XXS',
    'new_download_bytes': 47039860096,
    'shared_lookup_bytes': 28800138432,
    'estimated_bytes_reclaimed': 106660000000,
    'delete_only_after_new_model_verified': True,
    'directories': [str(p) for p in directories],
    'files': [str(p) for p in files],
    'preserve': ['E:/Strata/engine', 'E:/Strata/.venv', 'E:/Strata-data/mtp',
                 'shared second shard, linked under the IQ3_XXS filename',
                 'qwen Codex profile, updated for IQ3_XXS', 'all GPT configuration'],
    'context':131072, 'auto_compact_token_limit':110000,
}
(root / 'iq3_xxs-migration-plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(plan, ensure_ascii=False, indent=2))
