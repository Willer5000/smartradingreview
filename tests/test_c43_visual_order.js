'use strict';
const assert = require('node:assert/strict');
const {sortSignalPresentation} = require('../static/signal_presentation_order_c43.js');
const cards = [
  {id:'1d3',symbol:'ETH', timeframe:'1D',tiempo_restante:3*86400},
  {id:'1h4',symbol:'XRP', timeframe:'1h',tiempo_restante:4*3600},
  {id:'30m1',symbol:'LINK', timeframe:'30m',tiempo_restante:3600},
  {id:'1d7',symbol:'BTC', timeframe:'1D',tiempo_restante:7*86400},
  {id:'30m2',symbol:'BTC', timeframe:'30m',tiempo_restante:7200},
  {id:'1h8',symbol:'ETH', timeframe:'1h',tiempo_restante:8*3600}
];
assert.deepEqual(sortSignalPresentation(cards).map(x=>x.id),[
  '30m2', '30m1', '1h8', '1h4', '1d7', '1d3'
]);
assert.deepEqual(cards.map(x=>x.id),['1d3','1h4','30m1','1d7','30m2','1h8']); // input immutable
assert.deepEqual(sortSignalPresentation(cards).map(x=>x.id).sort(),cards.map(x=>x.id).sort()); // no omissions/duplicates
const now = Date.UTC(2026,9,16,12,0,0);
assert.deepEqual(sortSignalPresentation([
  {id:'late',timeframe:'4h',valid_until:'2026-10-17T00:00:00Z'},
  {id:'soon',timeframe:'4h',source_valid_until:'2026-10-16T16:00:00Z'}
], now).map(x=>x.id),['late','soon']);
assert.deepEqual(sortSignalPresentation([
 {id:1,timeframe:'2h'},{id:2,timeframe:'2h'}
]).map(x=>x.id),[1,2]); // stable, unknown expiration
assert.deepEqual(sortSignalPresentation([]), []);
console.log('C43 ordering tests PASSED (Futures, Spot and Multi use this same sorter).');
