"""Shared PromptWatch-inspired onboarding frame; no dashboard styles."""
import html
from pathlib import Path

import p_mark


def _dashboard_link():
    """Only for someone with a finished dashboard to go back to. A new customer
    has none yet, and "/" would just loop them back to this setup page."""
    import accounts, db
    u = accounts.current()
    if u is None or u["is_admin"]:
        return DASHLINK
    done = db.one("SELECT 1 FROM scans s JOIN prompt_sets p ON p.id=s.prompt_set_id "
                  "JOIN user_stores us ON us.store_domain=p.store_domain "
                  "WHERE us.user_id=? AND s.status IN ('done','partial') LIMIT 1", (u["id"],))
    return DASHLINK if done else ""


DASHLINK = '<a class="dashboard-link" href="/">Back to dashboard <span aria-hidden="true">↗</span></a>'

E = html.escape

INTRO = '<p class="intro" id="preview-intro">See where your products stand when shoppers ask AI what to buy.</p>'
NOTE = '<p class="preview-note" id="preview-note">From your product listing to the questions buyers ask.</p>'

SAMPLE_STORY = '<div class="mini-dash" aria-label="Sample dashboard with illustrative data"><div class="md-head"><b>Visibility over time</b><span class="md-seg"><i>D</i><i class="on">W</i><i>M</i></span></div><div class="md-stats"><div><small>Trail Running Vest</small><strong data-to="38">38%%</strong><em class="up">↑ +12 pts</em></div><div><small>Insulated Water Bottle</small><strong data-to="9">9%%</strong><em class="dn">↓ −7 pts</em></div></div><svg class="mini-chart" viewBox="0 0 220 100" aria-hidden="true"><defs><linearGradient id="mu" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#32bd83" stop-opacity=".28"/><stop offset="1" stop-color="#32bd83" stop-opacity="0"/></linearGradient><linearGradient id="md" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e5484d" stop-opacity=".2"/><stop offset="1" stop-color="#e5484d" stop-opacity="0"/></linearGradient></defs><line x1="12" x2="208" y1="92.0" y2="92.0" class="g"/><line x1="12" x2="208" y1="60.0" y2="60.0" class="g"/><line x1="12" x2="208" y1="28.0" y2="28.0" class="g"/><path d="M12,92 L12.0,56.8 L40.0,60.0 L68.0,64.8 L96.0,68.0 L124.0,71.2 L152.0,74.4 L180.0,76.0 L208.0,77.6 L208,92 Z" fill="url(#md)"/><path d="M12,92 L12.0,69.6 L40.0,64.8 L68.0,60.0 L96.0,53.6 L124.0,47.2 L152.0,40.8 L180.0,36.0 L208.0,31.2 L208,92 Z" fill="url(#mu)"/><polyline points="12.0,56.8 40.0,60.0 68.0,64.8 96.0,68.0 124.0,71.2 152.0,74.4 180.0,76.0 208.0,77.6" class="ln dn"/><polyline points="12.0,69.6 40.0,64.8 68.0,60.0 96.0,53.6 124.0,47.2 152.0,40.8 180.0,36.0 208.0,31.2" class="ln up"/><line x1="208" x2="208" y1="8" y2="92" class="guide"/><circle cx="208" cy="31.2" r="3.5" class="pulse up"/><circle cx="208" cy="77.6" r="3.5" class="pulse dn"/><circle cx="208" cy="31.2" r="3.5" class="end up"/><circle cx="208" cy="77.6" r="3.5" class="end dn"/></svg><div class="md-axis"><span>3 Aug</span><span>21 Sep</span></div><p class="md-note">Sample data</p></div><script>(()=>{if(matchMedia(\'(prefers-reduced-motion: reduce)\').matches)return;document.querySelectorAll(\'.mini-dash [data-to]\').forEach(el=>{const to=+el.dataset.to,t0=performance.now()+250;const f=t=>{const k=Math.min(1,Math.max(0,(t-t0)/1100)),e=1-Math.pow(1-k,3);el.textContent=Math.round(to*e)+\'%%\';if(k<1)requestAnimationFrame(f);};el.textContent=\'0%%\';requestAnimationFrame(f);});})();</script>\n<div class="story-caption"><strong>It starts with your products</strong><p>Connect your store to choose what you’d like to track.</p></div>\n<div class="journey"><span>Store</span><i>→</i><span>Questions</span><i>→</i><span>Insights</span></div>\n'




def page(title, body, active, actions):
    names = ['Store', 'Brand', 'Catalog', 'Topics', 'Questions']
    progress = ''.join('<span class="segment %s" %s><b>%s</b><span>%s</span></span>' % (
        'complete' if i < active else 'active' if i == active else '',
        'aria-current="step"' if i == active else '', '✓' if i < active else i, E(name))
        for i, name in enumerate(names, 1))
    css = Path(__file__).with_name('onboarding.css').read_text()
    theme = Path(__file__).with_name('theme-graphite-onboarding.css')
    if theme.exists():  # dark Graphite look; delete the file to go back
        css += theme.read_text()
    glyphs = Path(__file__).with_name('sky-glyphs.svg').read_text()
    return (('''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>%s · Produkto</title><link rel="icon" type="image/png" href="/favicon.png?v=1"><link rel="apple-touch-icon" href="/favicon.png?v=1">
<link href="https://fonts.googleapis.com/css2?family=Onest:wght@400;500;600;700&family=Geist:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>%s</style></head><body class="step-%d"><div class="onboarding">
<section class="workspace"><header class="workspace-header"></header><div class="form-column">
<div class="setup-header"><nav aria-label="Setup progress: step %d of 5">%s</nav></div>
<main id="main">%s</main><footer><div class="actions">%s</div></footer>
</div></section>
<aside>{GLYPHS}<div class="sky" aria-hidden="true"><canvas class="starfield"></canvas>
<svg class="sky-logo" style="--x:10%%;--y:16%%;--s:42px;--r:-8deg"><use href="#i-openai"/></svg>
<svg class="sky-logo" style="--x:84%%;--y:12%%;--s:34px;--r:10deg"><use href="#i-claude"/></svg>
<svg class="sky-logo" style="--x:13%%;--y:82%%;--s:32px;--r:6deg"><use href="#i-gemini"/></svg>
<svg class="sky-logo" style="--x:88%%;--y:74%%;--s:38px;--r:-12deg"><use href="#i-grok"/></svg>
<svg class="sky-logo" style="--x:52%%;--y:94%%;--s:26px;--r:0deg"><use href="#i-aio"/></svg></div>
<div class="aside-inner"><p class="ai-pill"><span>We analyse your products using multiple AI models</span><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3.5 10.5 8 6 12.5"/></svg></p>
<h2 class="typing-title" aria-label="Your products. The next way to shop."><span class="typing-reserve" aria-hidden="true">Your products.<br>The next way to shop.</span><span class="typing-visible" aria-hidden="true">Your products.<br>The next way to shop.</span></h2>
{INTRO}
<div class="product-story{MARKCLS}" id="product-preview">
{STORY}</div>
{NOTE}
{DASHLINK}
</div></aside></div>
<script>
document.addEventListener('DOMContentLoaded',function(){
 // Starfield: same density, brightness and drift as the site's navy sections.
 (function(){const c=document.querySelector('.starfield');if(!c)return;const ctx=c.getContext('2d');
  const still=window.matchMedia('(prefers-reduced-motion: reduce)');let stars=[],w=0,h=0,frame=0;
  function resize(){const dpr=Math.min(2,window.devicePixelRatio||1);w=c.clientWidth;h=c.clientHeight;
   c.width=w*dpr;c.height=h*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);
   stars=Array.from({length:Math.round((w*h)/5200)},function(){return{x:Math.random()*w,y:Math.random()*h,
    r:Math.random()<0.9?0.35+Math.random()*0.6:1+Math.random()*0.5,depth:0.2+Math.random()*0.8,
    a:0.15+Math.random()*0.4,tw:Math.random()*Math.PI*2};});}
  function draw(now){const t=still.matches?0:now/1000;ctx.clearRect(0,0,w,h);ctx.fillStyle='#fff';
   for(const s of stars){const y=(((s.y-t*3*s.depth)%%h)+h)%%h;const x=(s.x+t*1.5*s.depth)%%w;
    ctx.globalAlpha=still.matches?s.a:s.a*(0.65+0.35*Math.sin(t*0.8+s.tw));
    ctx.beginPath();ctx.arc(x,y,s.r,0,Math.PI*2);ctx.fill();}
   if(!still.matches)frame=requestAnimationFrame(draw);}
  resize();window.addEventListener('resize',function(){resize();if(still.matches)draw(0);});
  document.addEventListener('visibilitychange',function(){if(document.hidden){cancelAnimationFrame(frame);frame=0;}
   else if(!frame&&!still.matches)frame=requestAnimationFrame(draw);});
  draw(0);})();
 const preview=document.getElementById('product-preview');
 const panel=preview.closest('aside');
 const reduced=window.matchMedia('(prefers-reduced-motion: reduce)');
 const typed=document.querySelector('.typing-visible');
 const titleText='Your products.\\nThe next way to shop.';
 let typingTimer=0, titleObserver;
 function finishTitle(){clearTimeout(typingTimer);typed.textContent=titleText;typed.classList.remove('is-typing');if(titleObserver)titleObserver.disconnect();}
 function startTitle(){
  if(reduced.matches){finishTitle();return;}
  let position=0;typed.textContent='';typed.classList.add('is-typing');
  function typeNext(){
   typed.textContent=titleText.slice(0,++position);
   if(position<titleText.length)typingTimer=setTimeout(typeNext,titleText[position-1]==='.'?220:42);
   else typingTimer=setTimeout(function(){typed.classList.remove('is-typing');},350);
  }
  typingTimer=setTimeout(typeNext,180);
 }
 if(!reduced.matches){
  typed.textContent='';
  titleObserver=new IntersectionObserver(function(entries){if(entries.some(function(e){return e.isIntersecting;})){titleObserver.disconnect();startTitle();}},{threshold:0.5});
  titleObserver.observe(typed.parentElement);
 }
 reduced.addEventListener('change',function(){if(reduced.matches)finishTitle();});

 const pointer=window.matchMedia('(hover: hover) and (pointer: fine)');
 let motionFrame=0, px=0, py=0;
 function resetMotion(){
  cancelAnimationFrame(motionFrame);motionFrame=0;
  preview.style.removeProperty('--tilt-x');preview.style.removeProperty('--tilt-y');
  preview.style.removeProperty('--drift-x');preview.style.removeProperty('--drift-y');
  panel.classList.remove('preview-engaged');
 }
 panel.addEventListener('pointermove',function(event){
  if(reduced.matches||!pointer.matches||event.pointerType==='touch')return;
  const bounds=panel.getBoundingClientRect();
  px=Math.max(-1,Math.min(1,(event.clientX-bounds.left)/bounds.width*2-1));
  py=Math.max(-1,Math.min(1,(event.clientY-bounds.top)/bounds.height*2-1));
  panel.classList.add('preview-engaged');
  if(!motionFrame)motionFrame=requestAnimationFrame(function(){
   preview.style.setProperty('--tilt-x',(-py*1.4)+'deg');
   preview.style.setProperty('--tilt-y',(px*1.8)+'deg');
   preview.style.setProperty('--drift-x',(px*3)+'px');
   preview.style.setProperty('--drift-y',(py*2)+'px');motionFrame=0;
  });
 });
 panel.addEventListener('pointerleave',resetMotion);
 panel.addEventListener('pointercancel',resetMotion);
 reduced.addEventListener('change',resetMotion);
 pointer.addEventListener('change',resetMotion);

 function setNote(id,text){var el=document.getElementById(id);if(el)el.textContent=text;}
 function showProduct(name,price,image){
  preview.replaceChildren();
  const label=document.createElement('div');label.className='story-top';label.textContent='YOUR SELECTED PRODUCT';preview.append(label);
  const frame=document.createElement('div');frame.className='preview-image';
  if(image){const img=document.createElement('img');img.src=image;img.alt=name;frame.append(img);}else{frame.textContent=name;}
  preview.append(frame);const caption=document.createElement('div');caption.className='story-caption';
  const title=document.createElement('strong');title.textContent=name;const detail=document.createElement('p');detail.textContent=price;
  caption.append(title,detail);preview.append(caption);
  setNote('preview-intro','The questions and insights that follow are built around this product.');
  setNote('preview-note','Your product is selected. Review its buyer questions next.');
 }
 document.querySelectorAll('#g .tile').forEach(function(tile){tile.addEventListener('click',function(){
  const bg=tile.querySelector('.im').style.backgroundImage;
  showProduct(tile.querySelector('.t').textContent,tile.querySelector('.p').textContent,bg.slice(5,-2));
  document.getElementById('product-next').textContent='Continue →';
 });});
 const selected=document.querySelector('.selected-product');
 if(selected){showProduct(selected.querySelector('strong').textContent,selected.querySelector('p').textContent.replace('View product ↗',''),selected.querySelector('img').src);
  setNote('preview-note','Review the questions on the left before starting your scan.');}
});
</script></body></html>''' % (E(title), css, active, active, progress, body, actions))
            .replace('{GLYPHS}', glyphs)
            .replace('{MARKCLS}', ' is-mark' if active == 1 else '')
            .replace('{INTRO}', '' if active == 1 else INTRO)
            .replace('{NOTE}', '' if active == 1 else NOTE)
            .replace('{DASHLINK}', _dashboard_link())
            .replace('{STORY}', p_mark.block() if active == 1 else SAMPLE_STORY))
