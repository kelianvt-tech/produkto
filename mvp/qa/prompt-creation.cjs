const {chromium}=require('/Users/kelianvantulder/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://localhost:8011/r/test/questions',{waitUntil:'domcontentloaded'});
 const open=async mode=>{await page.locator('#create-prompts').click();await page.locator(`[data-create="${mode}"]`).click();};
 await open('custom');await page.locator('#prompt-text').fill('Is this cleanser suitable for sensitive skin?\nHow does Shop Cleanser compare with alternatives?');await page.locator('.prompt-product-picker input').check();await page.locator('#prompt-submit').click();
 if(await page.locator('.prompt-review-card').count()!==2)throw Error('Multiline custom review failed');
 await page.locator('.prompt-review-card select').nth(1).selectOption('comparison');
 await Promise.all([page.waitForNavigation({waitUntil:'domcontentloaded'}),page.locator('#prompt-submit').click()]);
 if(await page.locator('[data-prompt-row]').count()!==2)throw Error('New prompts not persisted');
 await page.locator('#prompt-search').fill('alternatives');if(await page.locator('[data-prompt-row]:visible').count()!==1)throw Error('Search failed');await page.locator('#prompt-search').fill('');
 await open('upload');await page.locator('.prompt-product-picker input').check();await page.locator('#prompt-file').setInputFiles({name:'prompts.csv',mimeType:'text/csv',buffer:Buffer.from('prompt,notes\n"A cleanser, with gentle ingredients?",test')});await page.locator('#prompt-submit').click();await page.waitForSelector('.prompt-review-card');if(await page.locator('.prompt-review-card textarea').inputValue()!=='A cleanser, with gentle ingredients?')throw Error('CSV failed');await page.locator('#prompt-close').click();
 for(const mode of ['ai','keywords']){await open(mode);if(mode==='keywords')await page.locator('#prompt-keywords').fill('dry skin');await page.locator('#prompt-submit').click();await page.waitForSelector('#prompt-review:not([hidden])');if(await page.locator('.prompt-review-card textarea').inputValue()!=='Which cleanser suits dry skin?')throw Error('AI review failed');await page.locator('#prompt-close').click();}
 await page.locator('#create-prompts').click();await page.screenshot({path:'/tmp/produkto-prompts-desktop.png'});await page.keyboard.press('Escape');
 await page.setViewportSize({width:390,height:844});await open('custom');await page.screenshot({path:'/tmp/produkto-prompts-mobile.png'});if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Mobile page overflow');
 await page.keyboard.press('Escape');if(await page.locator('#prompt-dialog').evaluate(d=>d.open))throw Error('Escape failed');
 if(errors.length)throw Error(errors.join('\n'));console.log('Passed: custom multiline save, versioned pending list, search, CSV review, AI/keyword review (stubbed), mobile layout, Escape, no browser errors.');await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
