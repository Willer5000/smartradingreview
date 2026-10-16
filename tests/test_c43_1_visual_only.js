'use strict';
const assert = require('node:assert/strict');
const {
  sortSignalPresentation, uniqueSignalPresentation, preferRepresentative,
  riskRank, reconcileDerivativeLanes
} = require('../static/signal_presentation_order_c43.js');

// Orden: menor TF -> mayor vigencia -> menor riesgo; riesgo NO adelanta un TF
// ni vigencia distinta.
const entries = [
  {id:'high',symbol:'XRP-USDT',timeframe:'1h',tiempo_restante:14400,risk_class:'HIGH'},
  {id:'medium',symbol:'ETH-USDT',timeframe:'1h',tiempo_restante:14400,risk_class:'MEDIUM'},
  {id:'low',symbol:'BTC-USDT',timeframe:'1h',tiempo_restante:14400,risk_class:'LOW'},
  {id:'shortest',symbol:'SOL-USDT',timeframe:'30m',tiempo_restante:3600,risk_class:'HIGH'},
  {id:'longer',symbol:'LINK-USDT',timeframe:'1h',tiempo_restante:18000,risk_class:'HIGH'},
  {id:'daily',symbol:'BTC-USDT',timeframe:'1D',tiempo_restante:600000,risk_class:'LOW'}
];
const ordered = sortSignalPresentation(entries, Date.now(), {risk:true});
assert.deepEqual(ordered.map(s=>s.id), ['shortest','longer','low','medium','high','daily']);
assert.deepEqual(entries.map(s=>s.id), ['high','medium','low','shortest','longer','daily']);
// El C43 original sigue intacto para Spot: no se aplican tiers de riesgo.
assert.deepEqual(sortSignalPresentation(entries).map(s=>s.id),
 ['shortest','longer','high','medium','low','daily']);

const sameCell = [
  {id:'old',symbol:'BTC-USDT',timeframe:'30m',confidence:99,source_candle_close_timestamp:'2026-10-16T11:30:00Z'},
  {id:'new',symbol:'BTCUSDT',timeframe:'30M',confidence:78,source_candle_close_timestamp:'2026-10-16T12:00:00Z'},
  {id:'otherTF',symbol:'BTC-USDT',timeframe:'1h',confidence:85},
  {id:'newHighQuality',symbol:'BTC-USDT',timeframe:'30m',confidence:91,source_candle_close_timestamp:'2026-10-16T12:00:00Z'}
];
assert.deepEqual(uniqueSignalPresentation(sameCell).map(x=>x.id), ['otherTF','newHighQuality']);
assert.deepEqual(sortSignalPresentation(sameCell, Date.now(), {risk:true, dedupe:true}).map(x=>x.id),
 ['newHighQuality','otherTF']);
assert.equal(preferRepresentative(sameCell[1], sameCell[0]), true);
assert.equal(riskRank({manual_risk_class:'HIGH'}).tier > riskRank({manual_risk_class:'MEDIUM'}).tier, true);
assert.equal(riskRank({risk_class:'LOW'}).tier < riskRank({risk_class:'HIGH'}).tier, true);

function mockNode(obj) {
  return {
    style: {display:''},
    getAttribute(name) {return name==='data-str-signal' ? encodeURIComponent(JSON.stringify(obj)) : null;}
  };
}
const sharedKeyConfirmed = {id:'confirmed-new',symbol:'SOL-USDT',timeframe:'2h',confidence:86,
  source_candle_close_timestamp:'2026-10-16T12:00:00Z',activa:1};
const sharedKeyVigent = {id:'vigent-old',symbol:'SOL-USDT',timeframe:'2h',confidence:90,
  source_candle_close_timestamp:'2026-10-16T10:00:00Z',activa:1};
const secondActive = {id:'vigent-eth',symbol:'ETH-USDT',timeframe:'2h',confidence:85};
const confirmNodes=[mockNode(sharedKeyConfirmed)];
const vigentNodes=[mockNode(sharedKeyVigent), mockNode(secondActive)];
const confirmedPanel={dataset:{strLoaded:'1'},querySelectorAll(){return confirmNodes;}};
const activePanel={dataset:{strLoaded:'1'},querySelectorAll(){return vigentNodes;}};
const countConfirmed={textContent:'',className:''};
const countVigent={textContent:'',className:''};
const doc={getElementById(id){return ({
  'prev-signals-list':confirmedPanel,'active-signals-list':activePanel,
  'prev-signals-count':countConfirmed,'active-signals-count':countVigent
})[id];}};
reconcileDerivativeLanes(doc);
assert.equal(confirmNodes[0].style.display, '');
assert.equal(vigentNodes[0].style.display, 'none');
assert.equal(vigentNodes[1].style.display, '');
assert.equal(countConfirmed.textContent,'1');
assert.equal(countVigent.textContent,'1');
// Si desaparece confirmada (usuario la guarda, nueva consulta), Vigente se vuelve
// visible: no hay supresión persistente ni alteración del estado de Guardian.
confirmNodes.length = 0;
reconcileDerivativeLanes(doc);
assert.equal(vigentNodes[0].style.display, '');
assert.equal(countConfirmed.textContent,'0');
assert.equal(countVigent.textContent,'2');
// Si solo hay un panel recibido, no modificar la tarjeta del otro.
confirmedPanel.dataset.strLoaded='0';
vigentNodes[0].style.display='block';
reconcileDerivativeLanes(doc);
assert.equal(vigentNodes[0].style.display,'block');
console.log('C43.1: orden TF/vigencia/riesgo, dedup por celda y carriles independientes OK');
