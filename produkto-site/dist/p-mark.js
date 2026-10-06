/* Shared Produkto particle mark, adapted from mvp/app/p_mark.py. */
(async function(){
 var host=document.querySelector('[data-p-mark]');if(!host)return;
 var canvas=host.querySelector('canvas'),ctx=canvas.getContext('2d');
 var still=window.matchMedia('(prefers-reduced-motion: reduce)');
 var fine=window.matchMedia('(hover: hover) and (pointer: fine)');

 var pointsText=await fetch('assets/p-points.txt').then(function(r){if(!r.ok)throw Error('P points unavailable');return r.text();});
 var dots=pointsText.trim().split(';').map(function(row,i){
  var p=row.split(',');
  return {hx:+p[0],hy:+p[1],edge:p[2]==='1',x:0,y:0,vx:0,vy:0,
          phase:i*0.618033988749895*Math.PI*2};
 });

 var w=0,h=0,unit=0,ox=0,oy=0,frame=0;
 // 3D: every dot sits on the front and back face; edge dots also fill the
 // side walls, so the P reads as a solid slab while it turns (the way
 // Algosoup's glyph sphere gets depth from far dots being dim and small).
 var DEPTH=0.07,WALL=[-0.5,0,0.5];
 function layout(){
  var dpr=Math.min(2,window.devicePixelRatio||1);
  w=canvas.clientWidth;h=canvas.clientHeight;
  if(!w||!h)return false;
  canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);
  ctx.setTransform(dpr,0,0,dpr,0,0);
  // Keep the approved mark size based on its visible layout box. The canvas
  // extends beyond that box so turns and pointer ripples have room to draw.
  unit=Math.min(host.clientWidth,host.clientHeight)*0.9;ox=w/2;oy=h/2;return true;
 }

 // Commerce glyphs for the P's front face: prices, rankings, getting picked.
 // Pre-rendered once to small sprites; drawImage is far cheaper than
 // fillText for ~800 glyphs a frame.
 var GLYPHS=['€','$','%','★','#1','↑','✓','tag','bag'],SPR=[],SP=28;
 function sprite(g){
  var c=document.createElement('canvas');c.width=c.height=SP;var x=c.getContext('2d');
  x.fillStyle='#fff';x.strokeStyle='#fff';x.lineWidth=2.2;x.lineJoin='round';x.lineCap='round';
  if(g==='tag'){x.beginPath();x.moveTo(5,14);x.lineTo(13,6);x.lineTo(23,6);x.lineTo(23,16);x.lineTo(15,24);x.closePath();x.stroke();x.beginPath();x.arc(18.5,10.5,1.8,0,7);x.fill();}
  else if(g==='bag'){x.strokeRect(6,11,16,13);x.beginPath();x.arc(14,11,4.5,Math.PI,0);x.stroke();}
  else{x.font='600 '+(g.length>1?15:19)+'px Geist, system-ui, sans-serif';x.textAlign='center';x.textBaseline='middle';x.fillText(g,SP/2,SP/2+1);}
  return c;
 }
 GLYPHS.forEach(function(g){SPR.push(sprite(g));});
 dots.forEach(function(d){d.g=(Math.random()*GLYPHS.length)|0;d.life=0;});
 var LIFE=2600,SHARE=0.1;  // ~10% of the fill shows a symbol at any moment
 var fill=dots.filter(function(d){return !d.edge;}).length;

 var panel=host.closest('aside')||host;
 var mx=0,my=0,active=false;
 function track(e){
  if(!fine.matches||e.pointerType==='touch'){active=false;return;}
  var b=canvas.getBoundingClientRect();mx=e.clientX-b.left;my=e.clientY-b.top;active=true;
 }
 function leave(){active=false;}
 panel.addEventListener('pointermove',track);
 panel.addEventListener('pointerleave',leave);
 panel.addEventListener('pointercancel',leave);

 var RADIUS=112,PUSH=1900,SPRING=0.055,DAMP=0.82,FOCAL=2.6;
 var angle=0,last=0,phase=0;

 function project(x,y,z,t){
  // Slow turn round the vertical axis, a slight fixed tilt, and a float.
  var c=Math.cos(angle),s=Math.sin(angle);
  var X=x*c+z*s,Z=-x*s+z*c;
  var tilt=0.16,ct=Math.cos(tilt),st=Math.sin(tilt);
  var Y=y*ct-Z*st;Z=y*st+Z*ct;
  var k=FOCAL/(FOCAL+Z);
  var bob=still.matches?0:Math.sin(t*0.0009)*0.018;
  return [ox+X*unit*k,oy+(Y+bob)*unit*k,Z,k];
 }

function paint(t){
  ctx.clearRect(0,0,w,h);
  // Match the onboarding mark's dot spacing at every displayed size.
  var detailScale=unit/360;
  for(var i=0;i<dots.length;i++){
   var d=dots[i];
   var zs=d.edge?WALL.concat([-1,1]):[-1,1];
   for(var j=0;j<zs.length;j++){
    var p=project(d.hx,d.hy,zs[j]*DEPTH,t);
    // Near dots bright and large, far dots dim and small.
    var near=Math.max(0,Math.min(1,(0.12-p[2])/0.24));
    ctx.globalAlpha=(d.edge?0.35:0.22)+near*(d.edge?0.6:0.55);
    ctx.fillStyle=d.edge?'#ffffff':'#dbe4f4';
    if(!d.edge&&zs[j]===-1&&d.life>0){
     // Glitch, Algosoup-style: no fades. The dot snaps to a symbol
     // (scrambling through a few first), flickers, then snaps back.
     var sz=10*p[3]*detailScale;ctx.globalAlpha=Math.min(1,ctx.globalAlpha+0.15);
     ctx.drawImage(SPR[d.g],p[0]+d.ux-sz/2,p[1]+d.uy-sz/2,sz,sz);
    }else{
     ctx.beginPath();ctx.arc(p[0]+d.ux,p[1]+d.uy,(d.edge?2:1.8)*p[3]*detailScale,0,Math.PI*2);ctx.fill();
    }
   }
  }
  ctx.globalAlpha=1;
 }

 dots.forEach(function(d){d.ux=0;d.uy=0;d.vx=0;d.vy=0;});
 function step(now){
  frame=0;
  var dt=last?Math.min(50,now-last):16;last=now;
  // Slow swing, ~35deg each way (a full turn shows the P mirrored as a 'q').
  if(!still.matches){phase+=dt*0.00045;angle=Math.sin(phase)*0.62;}
  for(var i=0;i<dots.length;i++){
   var d=dots[i];
   if(active){
    var p=project(d.hx,d.hy,-DEPTH,now);
    var dx=p[0]+d.ux-mx,dy=p[1]+d.uy-my,dist=Math.sqrt(dx*dx+dy*dy)||0.0001;
    if(dist<RADIUS){var f=(1-dist/RADIUS);f=f*f*PUSH/(dist+18);d.vx+=dx/dist*f*0.016;d.vy+=dy/dist*f*0.016;}
   }
   d.vx=(d.vx-d.ux*SPRING)*DAMP;d.vy=(d.vy-d.uy*SPRING)*DAMP;
   d.ux+=d.vx;d.uy+=d.vy;
  }
  if(!still.matches){
   var on=0,G=GLYPHS.length;
   for(var q=0;q<dots.length;q++){var e=dots[q];if(e.life<=0)continue;
    e.life-=dt;e.flip-=dt;
    if(e.flip<=0){
     if(e.roll>0){e.g=(e.g+1+((Math.random()*(G-1))|0))%G;e.roll--;e.flip=70;}   // scramble step
     else if(e.life<260&&!e.out){e.out=1;e.roll=2;e.flip=0;}                        // scramble out
     else{e.g=(Math.random()*G)|0;e.flip=900+Math.random()*1600;if(Math.random()<0.3)e.roll=3;} // occasional flip
    }
    if(e.life>0)on++;}
   for(var tries=0;tries<3&&on<fill*SHARE;tries++){var r=dots[(Math.random()*dots.length)|0];
    if(!r.edge&&r.life<=0){r.life=1800+Math.random()*2400;r.g=(Math.random()*G)|0;r.roll=3;r.flip=0;r.out=0;on++;}}
  }
  paint(now);
  if(!still.matches&&!document.hidden)frame=requestAnimationFrame(step);
 }

 function start(){
  if(!layout())return;
  host.classList.add('ready');
  if(still.matches){paint(0);return;}
  if(!frame)frame=requestAnimationFrame(step);
 }

 window.addEventListener('resize',function(){layout();if(still.matches)paint(0);});
 document.addEventListener('visibilitychange',function(){
  if(document.hidden){cancelAnimationFrame(frame);frame=0;}
  else if(!frame&&!still.matches)frame=requestAnimationFrame(step);
 });
 still.addEventListener('change',function(){
  cancelAnimationFrame(frame);frame=0;
  if(still.matches)paint(0);else frame=requestAnimationFrame(step);
 });

 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);
 else start();
})().catch(function(){ /* Keep the fallback label visible if the points cannot load. */ });
