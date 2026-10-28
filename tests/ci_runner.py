"""CI runner preserving failures in annotations and machine-readable reports."""
import json
import platform
import os
from pathlib import Path
import sys
import unittest


def main():
    suite=unittest.defaultTestLoader.discover('tests')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    data={'platform':platform.platform(),'python':platform.python_version(),'run':result.testsRun,'passed':result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
          'skipped':[(str(t),reason) for t,reason in result.skipped],
          'failures':[(str(t),trace) for t,trace in result.failures+result.errors]}
    report=Path('build/test-results-'+sys.platform+'.json');report.parent.mkdir(exist_ok=True)
    report.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f"::notice title=Validation {sys.platform}::{data['platform']} ; {data['run']} tests exécutés ; {data['passed']} réussis ; {len(data['skipped'])} ignorés ; {len(data['failures'])} échecs.",flush=True)
    for name,trace in data['failures']:
        encoded=trace.replace('%','%25').replace('\r','%0D').replace('\n','%0A')
        print(f'::error title={name}::{encoded}',flush=True)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        text=f"## Tests {sys.platform}\n\n{data['run']} exécutés, {data['passed']} réussis, {len(data['skipped'])} ignorés.\n"
        for name,trace in data['failures']:text+=f'\n### {name}\n\n```text\n{trace}\n```\n'
        Path(os.environ['GITHUB_STEP_SUMMARY']).write_text(text,encoding='utf-8')
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':raise SystemExit(main())
