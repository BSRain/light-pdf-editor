"""Generated continuous-zoom burst with real Qt/worker responses."""
import argparse,json,tempfile,time,statistics,math
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from benchmark_editor import make_document, wait_until
from pdf_editor import Editor
from version import __version__


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    app=QApplication.instance() or QApplication([])
    e=Editor();e.show();result=dict(version=__version__,scope='Generated fixtures; Qt zoom calls and event processing, real worker tile replies. One burst per fixture, not a general latency guarantee.',cases={})
    temporary = tempfile.TemporaryDirectory()
    directory = temporary.name
    try:
        for kind in ('text','vector','image'):
            path=Path(directory)/(kind+'.pdf');make_document(path,kind)
            e.open_pdf(str(path));wait_until(lambda: e.path==path and not e.busy,e)
            wait_until(lambda: not e.tile_timer.isActive() and e.client.active is None and not e.client.tiles,e)
            replies=[]
            def record(response):
                request=response['request']
                if request['kind']=='tile':
                    scale=min(10,max(.25,math.ceil(e.view.zoom*e.view.devicePixelRatioF()*4)/4))
                    replies.append(dict(scale=request['scale'],obsolete=request['scale']!=scale))
            e.client.result.connect(record)
            durations=[]
            for base in (2.8,3.6,2.4):
                e.view.set_zoom(base);e.schedule_tiles()
                for n in range(10):
                    start=time.perf_counter();e.view.set_zoom(base*(1.012**(n+1)));app.processEvents()
                    durations.append((time.perf_counter()-start)*1000);QTest.qWait(16)
            started=time.perf_counter()
            wait_until(lambda: not e.tile_timer.isActive() and e.client.active is None and not e.client.tiles,e)
            result['cases'][kind]=dict(tile_replies=len(replies),obsolete_scale_replies=sum(r['obsolete'] for r in replies),
                zoom_event_p50_ms=round(statistics.median(durations),2),settle_ms=round((time.perf_counter()-started)*1000,2),
                visible_tiles=len(e.tile_items),cache_bytes=e.cache_bytes)
            e.client.result.disconnect(record)
    finally:
        e.dirty=False;e.cancel(local=True);e.close();temporary.cleanup()
    Path(args.output).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
