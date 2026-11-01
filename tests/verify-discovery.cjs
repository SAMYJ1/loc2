// Run against a supplied, real runtime module. All network dependencies are fake.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {EventEmitter} = require('node:events');
const source = fs.readFileSync(process.argv[2], 'utf8');
const mod = {exports:{}};
const context = {exports:mod.exports,module:mod,Buffer,console,Date,
  require:name => name === 'multicast-dns' ? ()=>{throw Error('Unexpected real multicast construction')} : require(name),
  setInterval:()=>({unref(){}}),clearInterval(){},setTimeout:()=>({}),clearTimeout(){}};
vm.runInNewContext(source,context,{filename:'discovery-under-test.js'});
function harness() {
 const sockets=[],connections=[],messages=[];
 class Multicast extends EventEmitter {
  constructor(options) { super();this.options=options;this.responses=[];this.queries=[]; }
  query(packet,callback) { this.queries.push(packet);callback?.(null); }
  respond(packet,callback) { this.responses.push(packet);callback?.(null); }
  destroy() { this.destroyed=true; }
 }
 class Connection extends EventEmitter {
  setTimeout(){} write(){} destroy(){this.emit('close');}
 }
 const discovery=new mod.exports.Discovery('en0',{deviceId:'02:00:00:00:00:01',pk:'fixture',pi:'fixture'},'02:00:00:00:00:02',()=>true,x=>messages.push(x),{
  interfaces:()=>({en0:[{family:'IPv4',address:'192.0.2.1',internal:false},{family:'IPv6',address:'fe80::1',scopeid:12,internal:false}]}),
  mdns:options=>{const s=new Multicast(options);sockets.push(s);return s;},
  connect:options=>{connections.push(options);return new Connection();},setTimeout:()=>({}),clearTimeout(){},now:()=>0
 });
 return {discovery,sockets,connections,messages};
}
const h=harness();
try {
 assert.equal(h.sockets.find(s=>s.options.type==='udp6').options.interface,'fe80::1%en0');
 const service='phone._carplay-ctrl._tcp.local';
 const records=[{name:service,type:'SRV',ttl:120,data:{target:'phone.local',port:7000}},
                {name:'phone.local',type:'AAAA',ttl:120,data:'fe80::2'}];
 h.sockets[0].emit('response',{answers:records});
 assert.equal(h.connections.length,0,'Missing TXT must not permit probing an unknown phone');
 h.sockets[0].emit('response',{answers:[{name:service,type:'TXT',ttl:120,data:[Buffer.from('id=02:00:00:00:00:02')]}]});
 assert.equal(h.connections[0].host,'fe80::2%en0');assert.equal(h.connections[0].localAddress,'fe80::1%en0');
} finally {h.discovery.destroy();}
const failure=harness();
try {
 const v6=failure.sockets.find(s=>s.options.type==='udp6');v6.emit('warning',{code:'EINVAL'});v6.emit('ready');
 assert.equal(v6.destroyed,true);assert(!failure.messages.some(x=>x.includes('IPv6发现接口已就绪')));
 const v4=failure.sockets.find(s=>s.options.type==='udp4');v4.emit('ready');assert(v4.responses.length>0,'IPv4 fallback remains usable');
} finally {failure.discovery.destroy();}
console.log('PASS: named IPv6 zones, known-target gating and multicast failure handling; zero network I/O');
