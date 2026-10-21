'use strict';
const fs = require('fs');
const assert = require('assert');
const vm = require('vm');
const src = fs.readFileSync(__dirname + '/../static/futures.js','utf8');
const escape = src.match(/function futEscapeHtml\(value\) \{[\s\S]*?\n\}/);
const strategy = src.match(/function _futC461StrategyLine\(signal\) \{[\s\S]*?\n\}/);
assert(escape && strategy,'both rendering helpers must exist');
const context = {};
vm.createContext(context);
vm.runInContext(escape[0]+'\n'+strategy[0], context);
const render = context._futC461StrategyLine;
const cases = [
  [{strategy_family:'BREAKOUT_RETEST',action:'LONG'},'Estrategia:', 'Ruptura y retesteo'],
  [{strategy_family:'SWEEP_REVERSAL',action:'SHORT'},'Estrategia:', 'Reversión tras barrido de liquidez'],
  [{levels:{strategy_family:'TREND_PULLBACK'}},'Estrategia:', 'Retroceso de tendencia'],
  [{operational_intelligence:{default_strategy:{family:'RSI_TREND'}}},'Estrategia:', 'Tendencia RSI'],
  [{strategy_family:'NONE',setup_family:'STRUCTURE_RETEST'},'Setup técnico:', 'Retesteo de estructura'],
  [{context_strategy_family:'VWAP_SESSION_PULLBACK'},'Familia de contexto:', 'Retroceso hacia VWAP'],
  [{},'Estrategia:', 'No informada en esta señal'],
  [null,'Estrategia:', 'No informada en esta señal'],
];
for (const [row,pre,label] of cases) {
  const html = render(row);
  assert(html.includes(pre)&&html.includes(label),JSON.stringify([row,html]));
  assert.equal((html.match(/<div/g)||[]).length,1,'must be one line');
}
const malicious = render({strategy_family:'<img src=x onerror="alert(1)">'});
assert(!malicious.includes('<img'));
assert(malicious.includes('&lt;img'));
assert(!malicious.includes('title="Estrategia: <'));
assert(!src.includes('fetch(' + '"/api/strategy'), 'No additional strategy fetch');
for(const snippet of [
  '${_futC461StrategyLine(c)}',
  '${_futC461StrategyLine(r)}',
  '${_futC461StrategyLine(s)}',
  '${_futC461StrategyLine(sig)}',
]) assert(src.includes(snippet),'missing one lane '+snippet);
assert.equal((src.match(/\$\{_futC461StrategyLine\(/g)||[]).length,6,'six frontend surfaces including active and confirmed');
console.log('C46.1 JS: PASS (8 label cases, XSS, one-line, 6 surfaces)');
