const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('static/futures.js','utf8');
const match = source.match(/window\.loadClosedSavedSignalsHistory =\s*async function\(detailsEl\) \{[\s\S]*?\n\};\n\n\n\/\/ ============ Refrescar lista y KPIs/);
assert.ok(match, 'Function archive exists');
const rows = Array.from({length:7}, (_,idx)=>({
 id:`id-${idx}`,action:idx%2?'LONG':'SHORT',status:'tp_hit',entry_touched:true,
 entry:100+idx,take_profit:110+idx,stop_loss:95+idx,symbol:'TEST-USDT',timeframe:'1h',
 closed_at:new Date(Date.UTC(2026,9,12,idx)).toISOString(), pnl_usdt:idx+1,pnl_pct:idx+1,
}));
const container={innerHTML:''};
const details={open:true,dataset:{},querySelector(){return container;}};
const ctx={
 window:{},
 _futFetchBounded:async()=>({ok:true,json:async()=>({success:true,signals:rows})}),
 _statusBadge:()=>'<b>TP</b>',_formatPnl:(row)=>`+${row.pnl_usdt} USD`,
 futEscapeHtml:(x)=>String(x).replaceAll('&','&amp;'),
};
vm.runInNewContext(match[0].replace(/\n\n\n\/\/ ============ Refrescar lista y KPIs/, ''),ctx);
ctx.window.loadClosedSavedSignalsHistory(details).then(()=>{
  assert.equal((container.innerHTML.match(/openSavedSignalDetail/g)||[]).length,5,'only newest five clickable');
  assert.equal((container.innerHTML.match(/Resumen histórico · sin gráfico/g)||[]).length,2,'older two text only');
  assert.equal((container.innerHTML.match(/Entry:/g)||[]).length,7,'all retained original price labels');
  assert.ok(container.innerHTML.includes('id-6'), 'newest chart card');
  assert.ok(!/openSavedSignalDetail\('id-0'\)/.test(container.innerHTML),'oldest not clickable');
  console.log('PASS: archive 5 recent charts, older text, all summary');
}).catch(e=>{console.error(e);process.exit(1)});
