// --- ChatGPT screens (dark mode). Every question and answer is a real capture: CAPTURES-2026-10-20.md ---
const GPT_BG='#212121',GPT_SIDE='#171717',GPT_FIELD='#303030',GPT_TXT='#ececec',GPT_DIM='#9b9b9b',RED='#e5484d';
const CHATS=[
 {q:'What are the best dog leashes for my dog golden retriever?',rows:[['rw-front','Ruffwear Front Range Dog Leash With Padded Handle','€26.95','Best overall'],
   ['rw-crag','Ruffwear Crag Dog Leash Everyday Lead','€40.95',''],['halti','Halti Multifunctional Lead (Anatomía)','€34.99',''],
   ['rw-knot','Ruffwear Knot a Leash','€44.95',''],['ns-bungee','Non-stop dogwear Touring Bungee','','']]},
 {q:'What are the best running shoes under $100?',rows:[['nb-680','New Balance Fresh Foam 680v9','$85','Best overall value'],
   ['adizero-evo','adidas Adizero Evo SL','$99.97','Best for speed'],['saucony-ride18',"Saucony Men's Ride 18",'$96.88','Best daily trainer deal'],
   ['downshifter14',"Nike Men's Downshifter 14",'$49.97','Best budget pick']]},
 {q:'What is the best moisturizer for dry, sensitive skin?',rows:[['cerave','CeraVe Moisturizing Cream','approx. €10–16','Best overall'],
   ['lrp','La Roche-Posay Toleriane Dermallergo Cream','approx. €23',''],['avene','Avène Tolérance Control Soothing Skin Recovery Cream','approx. €19–25',''],
   ['vani','Vanicream Moisturizing Cream','','']]},
 {q:'Which magnesium glycinate supplement should I buy for better sleep?',rows:[['drbest',"Doctor's Best High Absorption Magnesium",'approx. €16–25','Best value'],
   ['vitobest','Vitobest Magnesium Bisglycinate','approx. €11',''],['thorne','Thorne Magnesium Bisglycinate','','']]},
];
const QUESTION=CHATS[0].q,ANSWER_IMGS=[...new Set(CHATS.flatMap(c=>c.rows.map(r=>r[0])))];
function g(s,X,Y,col,sz,w=400,al='left'){x.font=`${w} ${sz}px Geist`;x.fillStyle=col;x.textAlign=al;x.textBaseline='alphabetic';x.fillText(s,X,Y);}
function gptLogo(cx,cy,size){const d=size/64;GRID[0].forEach(p=>{x.fillStyle=GPT_TXT;x.fillRect(cx+p[0]*size-d/2,cy+p[1]*size-d/2,d+.6,d+.6);});}
function gptFrame(){x.fillStyle=GPT_BG;x.fillRect(0,0,W,H);x.fillStyle=GPT_SIDE;x.fillRect(0,0,260,H);
  gptLogo(54,54,34);['New chat','Search chats','Library'].forEach((s,i)=>g(s,40,132+i*44,GPT_DIM,20));
  g('ChatGPT',300,62,GPT_TXT,24,600);}
// home view: "What can I help with?" with `n` characters of q typed into the box
function gptHome(q,n,lt){
  const cx=260+(W-260)/2,iw=860,ih=124,iy=600;gptFrame();g('What can I help with?',cx,500,GPT_TXT,44,400,'center');
  x.beginPath();x.roundRect(cx-iw/2,iy,iw,ih,34);x.fillStyle=GPT_FIELD;x.fill();const s=q.slice(0,n);
  if(n)g(s,cx-iw/2+30,iy+50,GPT_TXT,22);else g('Ask anything',cx-iw/2+30,iy+50,GPT_DIM,22);
  if((n>0&&n<q.length)||cursor(lt)){x.font='400 22px Geist';x.fillStyle=GPT_TXT;x.fillRect(cx-iw/2+30+x.measureText(s).width+2,iy+30,2,26);}
  g('+',cx-iw/2+30,iy+104,GPT_DIM,30);x.beginPath();x.arc(cx+iw/2-40,iy+90,20,0,7);x.fillStyle=n?GPT_TXT:'#676767';x.fill();
  g('↑',cx+iw/2-40,iy+98,GPT_BG,24,600,'center');
}
// answer view: the question as the user's message, then `shown` rows (fractional = popping in)
function gptAnswer(c,shown,miss){
  gptFrame();const L=520,R=W-160;x.font='400 22px Geist';const qw=x.measureText(c.q).width+48;
  x.beginPath();x.roundRect(R-qw,110,qw,60,30);x.fillStyle=GPT_FIELD;x.fill();g(c.q,R-qw+24,148,GPT_TXT,22);
  c.rows.forEach(([k,name,price,tag],i)=>{const kk=ease(cl(shown-i));if(kk<=0)return;const Y=210+i*148;x.globalAlpha=kk;
    x.beginPath();x.roundRect(L,Y,1180,130,18);x.fillStyle='#2a2a2a';x.fill();
    x.save();x.beginPath();x.roundRect(L+12,Y+12,106,106,12);x.clip();x.drawImage(IMG[k],L+12,Y+12,106,106);x.restore();
    g((i+1)+'. '+name,L+142,Y+56,GPT_TXT,26,600);if(price)g(price,L+142,Y+96,GPT_DIM,24);
    if(tag){x.font='600 20px Geist';const tw=x.measureText(tag).width+30;x.beginPath();x.roundRect(L+1180-tw-20,Y+20,tw,38,19);x.fillStyle='#3a3a3a';x.fill();g(tag,L+1180-tw/2-20,Y+46,GPT_TXT,20,600,'center');}
    x.globalAlpha=1;});
  if(miss>0){const k=ease(miss),Y=210+c.rows.length*148+16;x.globalAlpha=k;  // the verdict: your product is not in this answer
    x.beginPath();x.roundRect(L,Y,1180,96,18);x.fillStyle='rgba(229,72,77,.16)';x.fill();x.lineWidth=3;x.strokeStyle=RED;x.stroke();
    g('✕  Your product: not in this answer',L+36,Y+60,RED,34,600);x.globalAlpha=1;}
}
// shot 2: the leash question typed, camera pushing in on the box
function question(lt){
  const cx=260+(W-260)/2,fy=600+62,k=ease(cl((lt-.18)/.5)),z=1+1.05*k,px=W/2+(cx-W/2)*k,py=H/2+(fy-H/2)*k;
  x.setTransform(z,0,0,z,W/2-px*z,H/2-py*z);
  gptHome(QUESTION,Math.min(QUESTION.length,Math.floor(Math.max(0,lt-.25)*48)),lt);x.setTransform(1,0,0,1,0,0);
}
// shot 3: the leash answer, full screen
function answer(lt){const z=1.06-.06*ease(lt/.25);x.setTransform(z,0,0,z,W/2*(1-z),H/2*(1-z));
  gptAnswer(CHATS[0],(lt-.1)/.09,0);x.setTransform(1,0,0,1,0,0);}
// shots 4-6: four ChatGPT windows in a 2x2 grid
const CELL=[[0,0],[1,0],[0,1],[1,1]];
function cell(i,zoomIn,draw){ // zoomIn 0..1: 1 = this window full screen (used for the pull-out from shot 3)
  const gap=10,cw=(W-gap)/2,ch=(H-gap)/2,[cxI,cyI]=CELL[i],X=cxI*(cw+gap),Y=cyI*(ch+gap);
  const s=.5+(1-.5)*zoomIn,ox=X*(1-zoomIn),oy=Y*(1-zoomIn),w=W*s,h=H*s;
  x.save();x.beginPath();x.rect(ox,oy,w,h);x.clip();x.setTransform(s*(W/W),0,0,s*(H/H),ox,oy);x.scale(1,1);
  x.setTransform(w/W,0,0,h/H,ox,oy);draw();x.restore();x.setTransform(1,0,0,1,0,0);
}
function quadType(lt){ // the leash window shrinks to top-left while three more questions get typed
  fill(NAVY);const pull=1-ease(cl(lt/.28));
  for(let i=1;i<4;i++){const c=CHATS[i],t0=.22+(i-1)*.08,n=Math.min(c.q.length,Math.floor(Math.max(0,lt-t0)*70));
    if(lt>.12)cell(i,0,()=>gptHome(c.q,n,lt));}
  cell(0,pull,()=>gptAnswer(CHATS[0],9,0));
}
function quadAnswer(lt){fill(NAVY);for(let i=0;i<4;i++)cell(i,0,()=>gptAnswer(CHATS[i],i?(lt-.06-i*.05)/.08:9,0));}
function quadMiss(lt){fill(NAVY);
  for(let i=0;i<4;i++)cell(i,0,()=>gptAnswer(CHATS[i],9,cl((lt-.05-i*.09)/.15)));
  if(lt>.5){const k=ease(cl((lt-.5)/.12));x.fillStyle=`rgba(7,16,31,${(.9*k).toFixed(2)})`;x.fillRect(0,H/2-120,W,240);
    x.globalAlpha=k;txt('Your products? Not in any of them.',W/2,H/2+30,'#ffffff',92,700,'center');x.globalAlpha=1;}
}
