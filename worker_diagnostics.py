"""Local worker diagnostics. Request contents and passwords are never serialized."""
from datetime import datetime
import os
from pathlib import Path
import tempfile
from uuid import uuid4


def write_worker_log(message, request, stderr):
    request = request or {}
    details = (f'{datetime.now().isoformat()}\n{message}\n'
               f"Request kind: {request.get('kind', 'startup')}; id: {request.get('id', '-') }\n"
               f'Stderr tail (may include local paths or document details):\n{stderr[-4000:]}\n')
    bases = (Path(os.environ.get('LOCALAPPDATA', tempfile.gettempdir()))/'LightPDFEditor'/'logs',
             Path(tempfile.gettempdir())/'LightPDFEditor-logs')
    for base in bases:
        try:
            base.mkdir(parents=True, exist_ok=True)
            path = base / ('worker-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:8] + '.log')
            path.write_text(details, encoding='utf-8')
            return path
        except OSError:
            continue
    return None
