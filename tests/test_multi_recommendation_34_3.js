// Run: node tests/test_multi_recommendation_34_3.js
// Exercises the exact pure UI helper extracted from static/script.js (no network,
// no full Flask app, no Heavy Worker, no investment decision changes).
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const js = fs.readFileSync(path.join(__dirname, '..', 'static', 'script.js'), 'utf8');
const html = fs.readFileSync(path.join(__dirname, '..', 'templates', 'index.html'), 'utf8');
const begin = js.indexOf('window.renderMultiCachedRecommendation343 = function(');
const end = js.indexOf('\nwindow.commit18MultiIdentityReset = function(', begin);
assert.ok(begin > 0 && end > begin, 'Missing rendering function in full script.js');
const block = js.slice(begin, end);
let calls = 0;
const rec = {dataset: {}, innerHTML: '<div class="spinner">loading</div>', children: [], prepend(node) {this.children.unshift(node);},
  replaceChildren(node) {this.children = [node]; this.innerHTML = node.textContent;}};
const opts = {symbol: 'CL-USDT', tf: '4h'};
const els = {'symbol-select': {get value(){return opts.symbol;}}, 'interval-select':{get value(){return opts.tf;}},
  'system-recommendation': rec, 'rec-badge-mini':{textContent:'ESPERANDO'},
  'chart-title':{innerHTML:''}, 'formation-timeframe':{textContent:''},
  'pattern-4-timeframe':{textContent:''}, 'op-timeframe':{textContent:''},
  'rec-symbol':{textContent:''},'op-live-price':{textContent:''}};
const window = {IS_MULTI_ASSET_PAGE:true, IS_FUTURES_PAGE:true, PAGE_CONFIG:{defaultSymbol:'CL-USDT',defaultTimeframe:'4h',symbols:{'CL-USDT':'CL (WTI)','XAG-USDT':'XAG (Plata)'},timeframes:{'4h':'4 Horas','1h':'1 Hora'}},
 updateRecommendation(result) {calls++; rec.innerHTML=`RECOMMENDATION: ${result.decision.action}`;}};
const document = {getElementById(id){return els[id]||null;},createElement(tag){return {tagName:tag, className:'',textContent:'',setAttribute(k,v){this[k]=v;}};}};
vm.runInNewContext(block, {window, document, console});
const record = {symbol:'CL-USDT', timeframe:'4h',source_candle_close_timestamp:'2026-10-10T08:00:00Z',decision:{action:'LONG',confidence:87.6},levels:{entry:89.57,stop_loss:88,take_profit:93}};
assert.equal(window.renderMultiCachedRecommendation343(record,'CL-USDT','4h'),true);
assert.equal(calls,1);
assert.ok(rec.innerHTML.includes('LONG'));
assert.ok(rec.children[0].textContent.includes('No es una nueva señal LIVE'));
assert.ok(rec.children[0].textContent.includes('2026-10-10'));
assert.equal(window.renderMultiCachedRecommendation343(record,'CL-USDT','4h'),true);
assert.equal(calls,1,'Repeated BUSY polls must not repaint same recommendation');
assert.equal(window.renderMultiCachedRecommendation343({symbol:'CL-USDT',timeframe:'4h',df:{time:[]}},'CL-USDT','4h'),false,
  'A chart-only display must NEVER become a trade recommendation');
assert.equal(window.renderMultiCachedRecommendation343({...record,symbol:'XAG-USDT'},'CL-USDT','4h'),false,
  'Stale-identity partial must not overwrite current asset');
opts.symbol='XAG-USDT';
assert.equal(window.renderMultiCachedRecommendation343(record,'CL-USDT','4h'),false,
  'Response from previous selection must be ignored');
assert.equal(window.renderMultiCachedRecommendation343(record,'XAG-USDT','4h'),false);
assert.equal(calls,1);
// Multi identity reset invalidates former reference without touching market/trading code.
assert.ok(js.includes('window.__MULTI_RECOMMENDATION_SELECTED_CELL__ !== newCell'));
assert.ok(js.includes('window.renderMultiCachedRecommendation343?.(data.data, symbol, interval)'));
assert.ok(js.includes('selectedSymbol !== requestedSymbol || selectedTf !== requestedTf'));
assert.ok(js.includes('const visibleCachedMulti = Boolean('));
assert.ok(js.includes('Multi full result: descartado resultado tardío de otra celda'));
assert.ok(html.includes('COMMIT34-3-MULTI-RECOMMENDATION'));
assert.ok(html.includes('{% if is_multiasset|default(false) %}'));
// Execute the REAL 202 handler from the full UI bundle, not just the helper.
const busyStart = js.indexOf('if (window.IS_FUTURES_PAGE && data?.busy) {', js.indexOf('window.runCompleteAnalysis = function()'));
const busyEnd = js.indexOf('if (window.IS_FUTURES_PAGE) window.__FUTURES_SERVER_BUSY_UNTIL__ = 0;', busyStart);
assert.ok(busyStart > 0 && busyEnd > busyStart);
const busyHandler = vm.runInNewContext(`(function(data,symbol,interval){${js.slice(busyStart,busyEnd)}})`,
  {window, document, console, Date, setTimeout(){return 1;}, clearTimeout(){}, updateInstantRecommendation(){}, updateRecommendation:window.updateRecommendation});
window.setTimeout=()=>1;
opts.symbol='CL-USDT'; opts.tf='4h';
rec.dataset={}; rec.innerHTML='<div class="spinner">loading</div>'; rec.children=[];
window.currentAnalysis=null; window.__FUTURES_ANALYSIS_BUSY_RETRIES__=1;
const countBefore=calls;
busyHandler({busy:true,partial:true,data:record,retry_after_ms:25000},'CL-USDT','4h');
assert.equal(calls,countBefore+1,'Actual 202 handler must render central recommendation');
assert.ok(!rec.innerHTML.includes('spinner'),'BUSY+partial must NOT leave infinite spinner');
assert.equal(rec.dataset.multiCachedCell,'CL-USDT|4h');
opts.symbol='XAG-USDT';
rec.innerHTML='<div>New selection waiting</div>'; rec.dataset={};
const beforeStale=calls;
busyHandler({busy:true,partial:true,data:record,retry_after_ms:25000},'CL-USDT','4h');
assert.equal(calls,beforeStale,'Late 202 must not render previous selection');
assert.ok(!rec.dataset.multiCachedRevision);
assert.ok(!rec.innerHTML.includes('RECOMMENDATION: LONG'));

console.log('PASS: multi 34.3 helper and real 202 handler, historical provenance, identity, dedup, no fake LIVE');
