/* Offline DOM/Plotly smoke tests. No network, no server or signals.
   node tests/test_c39_visual_layers.js */
const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const text=fs.readFileSync(path.resolve(__dirname,'../static/script.js'),'utf8');
const helper=text.slice(text.indexOf('// C39 — Visual-only layer retention.'),text.indexOf('function updateFVGAOBChart(data) {'));
function fragment(a){const x=text.indexOf('function '+a+'(data) {');assert(x>=0,a);const y=text.indexOf('\nfunction ',x+8);return text.slice(x, y<0?text.length:y);}
const nodes=new Map();
function dom(id){ if(!nodes.has(id)) nodes.set(id,{id,dataset:{},data:[],innerHTML:'',style:{},insertAdjacentElement(_where,child){nodes.set(child.id,child)},get parentElement(){return null}});return nodes.get(id);}
const storage=new Map();
let now=Date.now();
const sessionStorage={setItem:(k,v)=>storage.set(k,v),getItem:k=>storage.get(k)||null,removeItem:k=>storage.delete(k),key:i=>[...storage.keys()][i],get length(){return storage.size}};
const selection={symbol:'BTC-USDT',tf:'1h'};
const document={getElementById(id){if(id==='symbol-select')return {value:selection.symbol};if(id==='interval-select')return {value:selection.tf};return dom(id)},createElement(tag){return {tagName:tag,hidden:false,style:{},setAttribute(){}}}};
const plots=[];
const Plotly={purge(el){const x=typeof el==='string'?dom(el):el;x.data=[];},newPlot(id,traces,layout){const x=typeof id==='string'?dom(id):id;x.data=traces;plots.push(id);return Promise.resolve()},react(id,traces,layout){return this.newPlot(id,traces,layout)},restyle(){return Promise.resolve()},addTraces(){return Promise.resolve()}};
const window={Plotly,IS_FUTURES_PAGE:true,IS_MULTI_ASSET_PAGE:false};
const context={window,document,sessionStorage,Plotly,Date,Math,JSON,Array,Number,Set,Map,console,Intl};
vm.runInNewContext(helper+'\n'+fragment('updateFVGAOBChart')+'\n'+fragment('updateLiquidationHeatmap'),context);
const x=Array.from({length:45},(_,i)=>new Date(2026,9,1,i).toISOString());
const close=x.map((_,i)=>105+i*.05+Math.sin(i/2)*.3);
const df={time:x,open:close.map(v=>v-.1),high:close.map(v=>v+.4),low:close.map(v=>v-.4),close,volume:x.map(()=>100)};
function data(extra={}){return {symbol:selection.symbol,timeframe:selection.tf,df,...extra};}
const structure={fair_value_gaps:[{index:38,type:'bullish',gap_bottom:100,gap_top:101}],order_blocks:[],liquidity_sweeps:[],stop_hunts:[]};
context.updateFVGAOBChart(data({structure}));
assert(plots.includes('fvg-ob-chart'),'genuine structure must plot');
const n1=plots.length;
context.updateFVGAOBChart(data());
assert(plots.length>n1,'cached structure must plot instead of disappearing');
assert(dom('fvg-ob-chart-c39-note').textContent.includes('histórica'));
selection.symbol='ETH-USDT';
context.updateFVGAOBChart(data());
assert(dom('fvg-ob-chart-c39-note').textContent.includes('OHLCV real'));
assert(storage.size===1,'different cell must not capture previous structure');
selection.symbol='BTC-USDT';
// Need fresh source-derived bin: no synthetic price-level assumptions.
const liquidation={active_bins:[{price_bottom:104,price_top:107,max_weight:1,weight:1,side:'long'}],frozen_bins:[],total_long_weight:1,total_short_weight:0};
context.updateLiquidationHeatmap(data({liquidation}));
assert(plots.some(p=>p==='liquidation-heatmap-chart'||p?.id==='liquidation-heatmap-chart'),'genuine liquidation must plot');
const n2=plots.length;
context.updateLiquidationHeatmap(data());
assert(plots.length>n2,'old real bins must restore without changing signals');
assert(dom('liquidation-heatmap-chart-c39-note').textContent.includes('HISTÓRICO'));
selection.symbol='ETH-USDT';
context.updateLiquidationHeatmap(data());
assert(!dom('liquidation-heatmap-chart').data?.length,'cannot display BTC liquidation on ETH');
assert(dom('liquidation-heatmap-chart').innerHTML.includes('Sin mapa'));
const visual=fs.readFileSync(path.resolve(__dirname,'../static/visual_recovery_c38.js'),'utf8');
assert(!visual.includes('preserveTechnicalDecision(() => window.updateAllCharts?.(data))'),'partial OHLCV must not reset rich panels');
assert(visual.includes('recoverLayers(data,req)'));
const index=fs.readFileSync(path.resolve(__dirname,'../templates/index.html'),'utf8');
assert(index.includes('20261012-C39-VISUAL-LAYERS'));
assert(!text.slice(text.indexOf('window.updateLiveVisualIndicators = function'),text.indexOf('window.updateLiveCandleOverlay = function')).includes("['liquidation-heatmap', 'liquidation-heatmap-chart', updateLiquidationHeatmap]"),'no redraw map at every open candle tick');
console.log('C39 PASS: real-layer preservation, session restore, isolated identity, honest OHLCV display-only fallback, no fake liquidation, safe visual recovery, low-frequency heavy map.');
