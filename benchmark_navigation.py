"""Page navigation baseline; generated documents, real worker pipe latency."""
import json
from pathlib import Path
import tempfile
from benchmark_workflows import Worker, make_fixture, summary
from version import __version__


def main():
    result = dict(version=__version__, scope='Worker request through JSON pipe to response; excludes UI painting. Generated fixtures only; no before/after speedup claim.', cases={})
    with tempfile.TemporaryDirectory() as directory:
        for kind in ('many_pages', 'large_page', 'large_images'):
            path = Path(directory) / (kind + '.pdf')
            fixture = make_fixture(path, kind)
            worker = Worker()
            try:
                data, opened = worker.call('open', path=str(path))
                turns, thumbnails = [], []
                for n in range(12):
                    index = (n * 7) % fixture['pages']
                    _, elapsed = worker.call('page', index=index)
                    turns.append(elapsed)
                    _, elapsed = worker.call('thumbnail', index=index, revision=data['revision'])
                    thumbnails.append(elapsed)
                result['cases'][kind] = dict(fixture=fixture, open_ms=round(opened,2), page_response=summary(turns), thumbnail_response=summary(thumbnails))
            finally:
                worker.close()
    target = Path('benchmarks/navigation-v0.6.0-rc.1.json')
    target.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
