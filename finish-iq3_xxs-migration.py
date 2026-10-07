"""Resume verification of an already loaded IQ3_XXS, using Strata's private Python environment."""
import importlib.util
import json
from pathlib import Path
import subprocess
import traceback

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('migration', ROOT / 'install-iq3_xxs-local.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def main():
    if (ROOT / 'iq3_xxs-migration.paused').exists():
        m.status('paused', waiting_for_user_to_continue=True)
        return
    plan = json.loads((ROOT / 'iq3_xxs-migration-plan.json').read_text())
    if plan.get('state') != 'approved':
        raise RuntimeError('Migration is not approved')
    health = m.request('/health')
    if not health.get('loaded') or health.get('model') != 'qwen3.8-flash-next-iq3_xxs' or health.get('max_context') != 131072:
        raise RuntimeError('Expected IQ3_XXS at 131072 tokens is not loaded')
    short = m.chat('Calcula 17 + 25. Responde solamente con el numero.')
    if short['choices'][0]['message'].get('content','').strip() != '42':
        raise RuntimeError('Basic answer test failed')
    m.status('testing_long_context', port=m.PORT)
    long = m.chat(m.long_context_prompt(), timeout=1200)
    answer = long['choices'][0]['message'].get('content','')
    if long['usage']['prompt_tokens'] < 100000 or 'contexto-verificado-128k' not in answer:
        raise RuntimeError('Long-context verification failed; IQ3_S retained')
    m.update_launchers_and_codex()
    report = {'health':health,'models':m.request('/v1/models'),'short_test':short,'long_test':long,
              'metrics':m.request('/metrics'),'auto_compact_token_limit':110000,'port':m.PORT}
    (ROOT / 'iq3_xxs-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    m.status('cleaning_old_model', long_prompt_tokens=long['usage']['prompt_tokens'], port=m.PORT)
    subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',
                    str(ROOT / 'remove-approved-iq3_s.ps1')],cwd=ROOT,check=True)
    plan['state']='complete'
    (ROOT / 'iq3_xxs-migration-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    m.status('verified',health=health,long_prompt_tokens=long['usage']['prompt_tokens'],long_test_answer=answer,
             old_iq3_s_removed=True,auto_compact_token_limit=110000,url=f'http://127.0.0.1:{m.PORT}')

if __name__=='__main__':
    try:
        main()
    except Exception as error:
        m.status('failed',error=str(error),traceback=traceback.format_exc(),old_model_retained=True)
        raise
