/* Offline transport + actual chart integration tests. node qa_commit17_5_11_frontend.js */
const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const read=n=>fs.readFileSync(path.join(__dirname,'static',n),'utf8');
let count=0;const ok=(name)=>{count++;console.log(`PASS ${count}: ${name}`)};
(async()=>{
 const src=read('futures.js');
 // Use the exact function, excluding the remainder of the app initialization.
 const end=src.indexOf('\n}\n')+3;
 const sandbox={AbortController,Response,Promise,setTimeout,clearTimeout,fetch:async()=>new Response('{"ok":true}')};
 vm.createContext(sandbox);vm.runInContext(src.slice(0,end),sandbox);
 assert.deepEqual(await(await sandbox._futFetchBounded('/signals')).json(),{ok:true});ok('GET result preserved');
 sandbox.fetch=()=>new Promise(()=>{});
 await assert.rejects(sandbox._futFetchBounded('/signals',{},5),/excedió/);ok('hung headers have deadline');
 sandbox.fetch=async()=>({arrayBuffer:()=>new Promise(()=>{})});
 await assert.rejects(sandbox._futFetchBounded('/signals',{},5),/excedió/);ok('hung response body has deadline');
 const sentinel={write:true};sandbox.fetch=async()=>sentinel;
 assert.equal(await sandbox._futFetchBounded('/saved',{method:'POST'}),sentinel);ok('writes retain original transport');
 const chartContext=hidden=>{
   const c={window:{IS_FUTURES_PAGE:true},localStorage:{getItem:()=>JSON.stringify({hidden})},
      document:{addEventListener:()=>{}},setTimeout:()=>0,console};vm.createContext(c);vm.runInContext(read('chart_workspace.js'),c);return c;
 };
 assert.equal(chartContext([]).window.ChartWorkspace.shouldRender('market-maker-options'),true);ok('options registered and visible by default');
 assert.equal(chartContext(['market-maker-options']).window.ChartWorkspace.shouldRender('market-maker-options'),false);ok('user hide preference preserved');
 const elements=new Map();const get=id=>{if(!elements.has(id))elements.set(id,{textContent:'',innerHTML:''});return elements.get(id)};
 let plots=[];
 const c={window:{Plotly:{react:(...args)=>plots.push(args),purge:()=>{}},updateAllCharts:()=>42},
     document:{getElementById:get,readyState:'complete'},setTimeout:()=>0,console};
 vm.createContext(c);vm.runInContext(read('market_maker_frontend.js'),c);
 const data={levels:{market_maker_context:{available:true,spot:100,observed_option_chain:false,
    gex_curve:[[90,2],[null,3],[100,4]],delta_curve:[[90,-1],[100,1]],theta_curve:[[90,-2],[100,-3]],zero_gamma_level:null,delta_neutral_level:null}}};
 assert.equal(c.window.updateAllCharts(data),42);
 assert.equal(plots[0][1].length,3);ok('analysis hook renders Delta Gamma and Theta');
 assert.equal(plots[0][2].shapes.length,1);ok('missing levels never draw price zero');
 assert.deepEqual(Array.from(plots[0][1][0].x),[90,100]);
 assert.deepEqual(Array.from(plots[0][1][0].y),[2,4]);ok('invalid curve pairs removed together');
 c.window.updateMarketMakerOptionsChart({});assert.match(get('mm-options-chart').innerHTML,/no disponible/);ok('unavailable data is explicit');
 for(const name of ['futures.js','script.js','chart_workspace.js','market_maker_frontend.js'])new vm.Script(read(name));
 ok('all four changed JavaScript files parse');
 console.log(`FRONTEND: ${count}/${count} PASS`);
})().catch(e=>{console.error(e);process.exitCode=1});
