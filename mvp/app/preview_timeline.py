"""Development-only simulated timeline, served on 8012. Never imported by app.

Reads the existing dashboard, replaces presentation data in memory, and blocks
POST requests. No database writes or model calls. python3 mvp/app/preview_timeline.py
"""
import datetime as dt
import json
import math
import re
from http.server import ThreadingHTTPServer
import app

original_view = app.view_result


def simulate(html):
    def read(name):
        return json.loads(re.search(r'<script type="application/json" id="'+name+r'">(.*?)</script>',html,re.S).group(1))
    products=read('ranking-data')
    data=read('visibility-data')
    start=dt.datetime(2026,8,10,12)
    scans=[]
    for w in range(6):
        sid=9000+w
        total=0; own_hits=0; own_ranks=0
        for i,p in enumerate(products):
            hits=max(0,round(22-i*.5+10*math.sin(w*.9+i*.8)))
            # A product missing from one week has no position that week.
            if i==4 and w==2: hits=0
            position=1+((i*1.2+w*(.65 if i%2 else -.55))%5)
            ranks=round(hits*position)
            p.setdefault('preview_scan',{})[str(sid)]=dict(hits=hits,ranks=ranks,count=hits)
            total+=hits
            if p['own']: own_hits+=hits;own_ranks+=ranks
        # Simulated own recommendations occupy distinct answers, up to n.
        n=200
        scans.append(dict(id=sid,ts=(start+dt.timedelta(weeks=w)).timestamp(),n=n,
                          own=[own_hits,own_ranks],mt=total,sv=[],comp=[]))
    total_mentions=sum(s['mt'] for s in scans)
    for p in products:
        p['scan']=p.pop('preview_scan')
        hits=sum(v['hits'] for v in p['scan'].values())
        ranks=sum(v['ranks'] for v in p['scan'].values())
        p.update(rate=100*hits/1200,share=100*hits/total_mentions,avg=ranks/hits if hits else None,count=hits)
    data['scans']=scans
    for name,value in [('ranking-data',products),('visibility-data',data)]:
        html=re.sub(r'(<script type="application/json" id="'+name+r'">).*?(</script>)',lambda m:m[1]+json.dumps(value).replace('<','\\u003c')+m[2],html,flags=re.S)
    # Update the existing tables before chart code consumes their rows.
    setup='''<script>
(()=>{const P=JSON.parse(document.getElementById('ranking-data').textContent);
const update=(row,p,offset)=>{const c=row.querySelectorAll('td');c[offset].textContent=Math.round(p.rate)+'%';
if(offset===2){c[3].textContent=p.share.toFixed(1)+'%';c[4].textContent=p.avg?'#'+p.avg.toFixed(1):'—';}
else{c[2].textContent=p.avg?p.avg.toFixed(1):'—';c[3].textContent=p.share.toFixed(1)+'%';c[4].textContent='Simulated';}};
document.querySelectorAll('.ranking-card tr[data-product]').forEach(r=>update(r,P[Number(r.dataset.product)],2));
document.querySelectorAll('.pc-table tbody tr').forEach(r=>{const p=P.find(p=>p.name===r.querySelector('b').textContent);if(p)update(r,p,1);});
const own=P.filter(p=>p.own),share=own.reduce((t,p)=>t+p.share,0);
document.querySelector('.kpi-cell[data-mode=sov] strong').innerHTML=share.toFixed(1)+'<small class="kpi-unit">%</small><small>Simulated</small>';
document.querySelector('.rank-head strong').textContent=P.reduce((t,p)=>t+p.count,0)+' mentions';
document.querySelectorAll('#rescan,.context-row nav,.chart-evidence').forEach(e=>e.remove());
})();</script>'''
    # Keep chart-evidence present because the chart toggles its visibility.
    setup=setup.replace('#rescan,.context-row nav,.chart-evidence','#rescan,.context-row nav')
    import insight_panels
    html=html.replace(insight_panels.CHART_SCRIPT,setup+insight_panels.CHART_SCRIPT)
    banner='<div style="padding:12px 24px;background:#fff3ce;color:#604500;font:14px system-ui;text-align:center">Simulated preview · Six fictional weeks · Your saved scans are unchanged · <a href="http://localhost:8010/">Return to real results</a></div>'
    html=re.sub(r'(<body[^>]*>)',lambda m:m[1]+banner,html,count=1)
    html=html.replace('</body>','<script>if(location.hash==="#position")document.querySelector(\'.kpi-cell[data-mode="position"]\').click();</script></body>')
    return html


def view(token,query=None):
    status,body=original_view(token,query)
    return status,simulate(body) if status==200 and 'id="ranking-data"' in body else body


class PreviewHandler(app.Handler):
    def do_POST(self):
        self.send_error(405,'Read-only simulated preview')


if __name__=='__main__':
    app.view_result=view
    print('Simulated preview: http://localhost:8012/r/j3GEFFdjQclSG9Fh?range=custom&from=2026-08-10&to=2026-09-20&group=week#position',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8012),PreviewHandler).serve_forever()
