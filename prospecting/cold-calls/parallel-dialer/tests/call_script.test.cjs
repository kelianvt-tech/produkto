const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// The call script shown in the call pop-up (static/call-script.js): the operator reads
// it aloud while talking, so it has to be readable, filled in for the person on the
// line, and never able to inject markup from the notepad's text.

const source = fs.readFileSync(path.join(__dirname, '../parallel_dialer/static/call-script.js'), 'utf8');

function load() {
  const context = { window: {} };
  vm.runInNewContext(source, context);
  return context.window.DialerCallScript;
}

test('fills the prospect, the operator and the company where the script has slots', () => {
  const { render } = load();
  const html = render('"Hey [Name], this is [My Name] with Acme. How is [Company] doing this quarter?"', {
    name: 'Jane', me: 'Alice', company: 'Globex Partners',
  });
  assert.match(html, /Hey <mark class="script-fill">Jane<\/mark>/);
  assert.match(html, /this is <mark class="script-fill">Alice<\/mark>/);
  assert.match(html, /How is <mark class="script-fill">Globex Partners<\/mark>/);
});

test('a slot with nothing to fill stays visible as a slot', () => {
  const { render } = load();
  assert.match(render('Hey [Name]', {}), /<mark class="script-slot">\[Name\]<\/mark>/);
});

test('reads as sections, objections, replies, cues and bullets', () => {
  const { render } = load();
  const html = render([
    '# 📞 TALK TRACK',
    '## 1. THE OPENER',
    '*Pause. Let them answer.*',
    '### "Just send me an email"',
    '👉 "Happy to do that right now."',
    '• "Do you offer fall detection?"',
    '• "How does your team find out?"',
  ].join('\n'));
  assert.match(html, /<h3 class="script-title">📞 TALK TRACK<\/h3>/);
  assert.match(html, /<h4 class="script-section">1\. THE OPENER<\/h4>/);
  assert.match(html, /<p class="script-cue">Pause\. Let them answer\.<\/p>/);
  assert.match(html, /<h5 class="script-objection">&quot;Just send me an email&quot;<\/h5>/);
  assert.match(html, /<p class="script-reply">&quot;Happy to do that right now\.&quot;<\/p>/);
  assert.match(html, /<ul><li>&quot;Do you offer fall detection\?&quot;<\/li><li>/);
});

test('never passes markup through from the notepad, or from a contact name', () => {
  const { render } = load();
  const html = render('<img src=x onerror=alert(1)> Hi [Name]', { name: '<b>Eve</b>' });
  assert.ok(!html.includes('<img'), html);
  assert.ok(!html.includes('<b>'), html);
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.match(html, /&lt;b&gt;Eve&lt;\/b&gt;/);
});

test('uses a first name, and none for the dialer\'s nameless stand-in', () => {
  const { firstName } = load();
  assert.equal(firstName('Jane Roe'), 'Jane');
  assert.equal(firstName('Dr. Jane Smith'), 'Jane');
  assert.equal(firstName('Karen Rue Rn-Bc'), 'Karen');
  assert.equal(firstName('Close contact'), '');
  assert.equal(firstName(''), '');
  assert.equal(firstName(undefined), '');
});
