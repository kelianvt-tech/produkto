"""The filling Produkto P as a full-page loader for waits that aren't scans.

Same look as the results-loading page (app.LOADING): the P's dots fill
bottom to top in navy. A scan reports real progress; these waits (the agent
reading pages, drafting a fix, checking products) don't, so the fill follows
the expected time on an easing curve that slows near the end and never
passes 92%. The next page replaces it when the work is done.

Use: put busy(label, seconds) on a form (an onsubmit attribute). app.page()
adds the overlay to any page whose body calls pLoad.
"""
import json
from html import escape as E
from pathlib import Path

_POINTS = ';'.join(row.rsplit(',', 1)[0] for row in
                   Path(__file__).with_name('p-points.txt').read_text().strip().split(';'))


def busy(label, seconds, button='button[type=submit],button:not([type])'):
    """onsubmit="..." that disables the form's button and shows the loader."""
    return 'onsubmit="var b=this.querySelector(%s);if(b)b.disabled=true;pLoad(%s,%d)"' % (
        E(json.dumps(button)), E(json.dumps(label)), seconds)


def markup():
    return """<div class="pl-wrap" id="pl-wrap" hidden><div class="pl-box">
<canvas id="pl-canvas" aria-hidden="true"></canvas>
<p class="pl-title" id="pl-title" role="status"></p>
<p class="pl-meta" id="pl-meta"></p></div></div>
<script>
(function(){
 var pts='%s'.split(';').map(function(r){var p=r.split(',');return {x:+p[0],y:+p[1],a:0};});
 pts.forEach(function(p,i){p.k=p.y+((i*0.618)%%1)*0.04;});
 pts.sort(function(a,b){return b.k-a.k;});
 var S=200,still=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
 window.pLoad=function(label,secs){
  var w=document.getElementById('pl-wrap'),c=document.getElementById('pl-canvas'),ctx=c.getContext('2d');
  var dpr=window.devicePixelRatio||1;c.width=c.height=S*dpr;c.style.width=c.style.height=S+'px';ctx.scale(dpr,dpr);
  document.getElementById('pl-title').textContent=label;
  document.getElementById('pl-meta').textContent='Usually about '+(secs<60?secs+' seconds':Math.round(secs/60)+' minute'+(secs>=120?'s':''));
  w.hidden=false;
  // Navy on light, the page's own text colour on dark.
  var rgb=(getComputedStyle(document.getElementById('pl-title')).color.match(/\\d+/g)||[11,27,53]).slice(0,3).join(',');
  var t0=Date.now(),shown=0;
  function frame(){
   var t=(Date.now()-t0)/1000,target=0.92*(1-Math.exp(-t/(secs*0.55)));
   shown+=(target-shown)*(still?1:0.08);
   var n=Math.round(shown*pts.length);ctx.clearRect(0,0,S,S);
   for(var i=0;i<pts.length;i++){var p=pts[i],on=i<n;p.a+=still?((on?1:0)-p.a):((on?1:0)-p.a)*0.08;
    ctx.fillStyle='rgba('+rgb+','+(0.09+0.91*p.a).toFixed(3)+')';ctx.fillRect(S/2+p.x*180-1.5,S/2+p.y*180-1.5,3,3);}
   requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
 };
 // Coming back with the browser's Back button restores the page as it was: hide the loader again.
 window.addEventListener('pageshow',function(e){if(e.persisted){var w=document.getElementById('pl-wrap');if(w)w.hidden=true;
  document.querySelectorAll('button[disabled]').forEach(function(b){b.disabled=false;});}});
})();
</script>""" % _POINTS


def mini(fraction, seconds_left):
    """A small filling P for a progress banner: filled to `fraction` (real progress), creeping on towards
    the next step over `seconds_left`, never past it. Dots scale with the mark, so it keeps its spacing."""
    return """<canvas class="pl-mini" width="56" height="56" aria-hidden="true" data-f="%.3f" data-s="%d"></canvas>
<script>(function(){var c=document.currentScript.previousElementSibling,ctx=c.getContext('2d'),S=56,
 d=window.devicePixelRatio||1,f=+c.dataset.f,secs=Math.max(15,+c.dataset.s),t0=Date.now();
 c.width=c.height=S*d;c.style.width=c.style.height=S+'px';ctx.scale(d,d);
 var pts='%s'.split(';').map(function(r){var p=r.split(',');return {x:+p[0],y:+p[1]};});
 pts.forEach(function(p,i){p.k=p.y+((i*0.618)%%1)*0.04;});pts.sort(function(a,b){return b.k-a.k;});
 var rgb=(getComputedStyle(c.parentNode).color.match(/\\d+/g)||[11,27,53]).slice(0,3).join(',');
 var still=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
 function frame(){var t=(Date.now()-t0)/1000,g=still?f:f+(Math.min(1,f+0.2)-f)*0.8*(1-Math.exp(-t/secs)),
  n=Math.round(g*pts.length),u=S*0.9,dot=Math.max(1,u/120);ctx.clearRect(0,0,S,S);
  for(var i=0;i<pts.length;i++){ctx.fillStyle='rgba('+rgb+','+(i<n?1:0.14)+')';
   ctx.fillRect(S/2+pts[i].x*u-dot/2,S/2+pts[i].y*u-dot/2,dot,dot);}
  if(!still)requestAnimationFrame(frame);}
 frame();})();</script>""" % (fraction, seconds_left, _POINTS)


CSS = """
.pl-mini{flex:none}
.pl-wrap{position:fixed;inset:0 0 0 var(--rail-w,0);z-index:50;display:grid;place-items:center;background:var(--bg,#f6f8fb)}
.pl-wrap[hidden]{display:none}
.pl-box{display:grid;justify-items:center;gap:6px;text-align:center;padding:24px}
.pl-title{font-size:20px;font-weight:700;color:#0b1b35;margin:14px 0 0}
.pl-meta{font-size:13.5px;color:#586579;margin:0}
"""
