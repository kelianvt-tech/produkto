const {chromium}=require('playwright');
(async()=>{const b=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});const p=await b.newPage({viewport:{width:1200,height:1000}});
for(const [name,url] of [['tally','https://www.lapa.ninja/post/tally-2/'],['duna','https://www.lapa.ninja/post/duna/'],['shiba','https://www.lapa.ninja/freebies/shiba-free-ui-kit-for-figma/']]){await p.goto(url);console.log((await p.locator('body').innerText()).slice(0,100));await p.screenshot({path:'mvp/qa/lapa-'+name+'.png'});console.log(name);}
await b.close();})();
