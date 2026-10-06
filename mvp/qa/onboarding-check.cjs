const {chromium}=require('playwright');
(async()=>{
const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
for(const width of [1440,375]){
 await page.setViewportSize({width,height:1000});
 for(const [name,path] of [['welcome','/new'],['brand','/brand?d=clubhouseskin.com'],['products','/store?d=clubhouseskin.com'],['prompts','/product?id=5']]){
 await page.goto('http://localhost:8010'+path);await page.waitForTimeout(300);
 await page.screenshot({path:`mvp/qa/${name}-${width}.png`,fullPage:true});
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
 if(overflow)throw new Error(name+' overflow at '+width);
 console.log(name,width,'OK');
 if(name==='products'){
  await page.locator('.tile').first().click();
  if(!await page.locator('#product-next').isEnabled())throw new Error('Product selection failed');
  await page.locator('#f').fill('no matching product 98765');
  if(!await page.locator('#no-products').isVisible())throw new Error('Empty search failed');
 }
 if(name==='brand'){
  await page.locator('#alias-add').click();
  await page.locator('.alias-row input').last().fill('Example alias');
  await page.locator('.alias-row button').last().click();
 }
 if(name==='prompts'){
  if(!await page.locator('#run').isEnabled())throw new Error('Scan button not initialized');
  if(await page.locator('#qbox textarea').count())throw new Error('Frozen questions editable');
 }
 }
}
if(errors.length)throw new Error(errors.join('\n'));
await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
