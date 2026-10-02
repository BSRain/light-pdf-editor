"""Cold and revisited page latency, generated fixtures and real worker IPC."""
import argparse
import json
from pathlib import Path
import tempfile
from benchmark_workflows import Worker, make_fixture, summary
from version import __version__


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = dict(version=__version__, scope='Real worker JSON request/response; excludes GUI painting. Cold means first metadata request after open, not OS cold cache.', cases={})
    with tempfile.TemporaryDirectory() as directory:
        for kind in ('many_pages', 'large_page', 'large_images'):
            path = Path(directory) / (kind + '.pdf')
            fixture = make_fixture(path, kind)
            worker = Worker()
            try:
                _, opened = worker.call('open', path=str(path))
                pages = min(4, fixture['pages'])
                cold = []
                for index in range(1, pages):
                    _, elapsed = worker.call('page', index=index)
                    cold.append(elapsed)
                warm = []
                for n in range(24):
                    _, elapsed = worker.call('page', index=n % pages)
                    warm.append(elapsed)
                result['cases'][kind] = dict(fixture=fixture, working_pages=pages, open_ms=round(opened,2),
                    first_visit=summary(cold) if cold else None, revisit=summary(warm))
            finally:
                worker.close()
    Path(args.output).write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
