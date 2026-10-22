// --- the agent rebuilds one product page so AI can quote it ---
// A generic "Your product" page: section names are real, the contents are bars, so no product facts are invented.
const PG={ink:'#0b1b35',mut:'#8a96a8',bar:'#dfe4ec',add:'#e9f8f0',green:'#2fbf71'};
function bars(X,Y,ws,h=16,col=PG.bar,gap=30){ws.forEach((w,i)=>{x.fillStyle=col;x.beginPath();x.roundRect(X,Y+i*gap,w,h,8);x.fill();});}
function section(X,Y,w,h,k){ // reveal: green "added" panel grows open
  const hh=h*ease(k);x.save();x.beginPath();x.rect(X-24,Y-10,w+48,hh+20);x.clip();
  x.fillStyle=PG.add;x.beginPath();x.roundRect(X-24,Y-10,w+48,h+20,14);x.fill();x.fillStyle=PG.green;x.fillRect(X-24,Y-10,6,h+20);return ()=>x.restore();}
const SECTIONS=[ // [start, x, y, w, h, draw]
 [.50,880,380,840,70,(X,Y)=>{g('Good for',X,Y+26,PG.ink,26,600);bars(X+150,Y+10,[520]);bars(X,Y+44,[640],14);}],
 [.64,880,490,840,130,(X,Y)=>{g('Key features',X,Y+26,PG.ink,26,600);[0,1,2].forEach(i=>{x.fillStyle=PG.green;x.fillRect(X,Y+52+i*30,10,10);bars(X+24,Y+48+i*30,[[560,480,520][i]],14);});}],
 [.78,880,650,840,170,(X,Y)=>{g('Specs',X,Y+26,PG.ink,26,600);['Material','Size','Weight','Care'].forEach((l,i)=>{const yy=Y+50+i*30;
   g(l,X,yy+14,PG.mut,20,400);bars(X+160,yy,[[300,220,160,380][i]],14);x.fillStyle=PG.bar;x.fillRect(X,yy+22,820,1);});}],
 [1.00,160,1000,1600,210,(X,Y)=>{g('How it compares',X,Y+26,PG.ink,26,600);['','This product','Alternative','Alternative'].forEach((h,i)=>g(h,X+360+i*300-300,Y+70,PG.mut,20,600));
   for(let r=0;r<3;r++){g(['Best for','Price','Rating'][r],X,Y+110+r*36,PG.mut,20);for(let c=0;c<3;c++)bars(X+360+c*300,Y+96+r*36,[[200,160,180][(r+c)%3]],14,c?PG.bar:'#bfe9d2');}}],
 [1.18,160,1250,1600,190,(X,Y)=>{g('FAQ',X,Y+26,PG.ink,26,600);[0,1,2].forEach(i=>{g('Q',X,Y+76+i*48,PG.green,24,700);bars(X+40,Y+62+i*48,[[700,560,640][i]],16);g('+',X+1560,Y+76+i*48,PG.mut,28);});}],
 [1.34,160,1480,1600,120,(X,Y)=>{g('Reviews',X,Y+26,PG.ink,26,600);g('★★★★★',X,Y+76,'#f2b01e',34);bars(X+210,Y+56,[420],16);bars(X+700,Y+56,[380],16);}],
];
function revamp(lt){
  fill('#ffffff');
  const scroll=560*ease(cl((lt-1.05)/.5)),Y0=-scroll;
  x.save();x.translate(0,Y0);
  // the page as it was: photo, name, price, one line, add to cart
  x.fillStyle='#f1f0ed';x.beginPath();x.roundRect(160,170,640,640,20);x.fill();
  x.strokeStyle='#c9ced8';x.lineWidth=10;x.beginPath();x.roundRect(370,400,220,250,18);x.stroke();x.beginPath();x.arc(480,400,60,Math.PI,0);x.stroke(); // a plain bag shape
  g('Your product',880,250,PG.ink,60,600);g('$48',880,310,PG.ink,34,400);
  if(lt<.5)bars(880,345,[560],14);
  x.fillStyle=PG.ink;x.beginPath();x.roundRect(880,lt<.5?400:860,420,74,37);x.fill();g('Add to cart',1090,lt<.5?447:907,'#ffffff',26,600,'center');
  // schema chips under the title
  if(lt>.92){const k=ease(cl((lt-.92)/.12));x.globalAlpha=k;let X=880;['✓ Product schema','✓ FAQ schema','✓ Review schema'].forEach(c=>{x.font='600 20px Geist';const w=x.measureText(c).width+32;
    x.fillStyle=PG.add;x.beginPath();x.roundRect(X,326,w,40,20);x.fill();g(c,X+16,353,PG.green,20,600);X+=w+12;});x.globalAlpha=1;}
  // the new sections, one by one
  SECTIONS.forEach(([t0,X,Y,w,h,draw])=>{if(lt<t0)return;const done=section(X,Y,w,h,cl((lt-t0)/.14));draw(X,Y);done();});
  // the agent: hops from section to section as it writes
  const cur=SECTIONS.filter(sct=>lt>=sct[0]-.08).pop();
  if(lt>.3&&lt<1.75){let tx=1500,ty=200;if(cur){tx=cur[1]+cur[3]-40;ty=cur[2]+8;}const bob=Math.sin(lt*40)*3;
    const ar=ease(cl((lt-.3)/.15));bot(tx+(1-ar)*300,ty-30+bob-(1-ar)*200,7,PG.ink,Math.floor(lt*6)%3===0);}
  x.restore();
  // browser bar on top
  x.fillStyle='#0b1b35';x.fillRect(0,0,W,96);x.fillStyle='#16294a';x.beginPath();x.roundRect(520,24,880,48,24);x.fill();
  g('yourstore.com/products/your-product',960,56,'#c7d2e4',22,400,'center');
  if(lt>.3&&lt<1.75){bot(1520,48,4,'#ffffff',false);g('Agent editing…',1550,56,'#ffffff',20,600);}
  // done: ready to be cited
  if(lt>=1.8){const k=ease(cl((lt-1.8)/.1));x.fillStyle=`rgba(7,16,31,${(.55*k).toFixed(2)})`;x.fillRect(0,96,W,H-96);
    x.globalAlpha=k;const w=900,h=120;x.fillStyle=PG.green;x.beginPath();x.roundRect(W/2-w/2,H/2-h/2,w,h,60);x.fill();
    g('✓  Ready to be cited by AI',W/2,H/2+18,'#ffffff',48,600,'center');x.globalAlpha=1;}
}
