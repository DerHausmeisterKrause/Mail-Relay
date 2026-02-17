const app = document.getElementById('app');
let token = localStorage.getItem('token') || '';

const esc = (s='') => String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');

function loginView(){
  app.innerHTML = `<div class="card" style="max-width:420px;margin:auto">
    <h2>Login</h2><p class="muted">Default: admin / Admin123</p>
    <input id="u" value="admin" placeholder="Username"><input id="p" type="password" value="Admin123" placeholder="Password">
    <button id="l">Anmelden</button><pre id="m"></pre></div>`;
  document.getElementById('l').onclick = async ()=>{
    const r = await fetch('/api/login',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({username:u.value,password:p.value})});
    const d = await r.json(); if(!r.ok){m.textContent=d.detail||'Login fehlgeschlagen'; return;}
    token=d.token; localStorage.setItem('token',token); mainView();
  }
}

async function api(path,opt={}){ opt.headers=Object.assign({},opt.headers||{}, {'Authorization':'Bearer '+token,'content-type':'application/json'}); const r=await fetch(path,opt); return [r, await r.json()]; }

function clusterForm(c){
  return `<div class="card"><h3>Cluster / Node / TLS / SSH</h3>
  <div class="row"><div><label>Node ID</label><input id="node_id" value="${esc(c.node_id)}"></div><div><label>Node IP</label><input id="node_ip" value="${esc(c.node_ip)}"></div></div>
  <div class="row"><div><label>Peer Node IP</label><input id="peer_ip" value="${esc(c.peer_node_ip)}"></div><div><label>VIP</label><input id="vip" value="${esc(c.vip_address)}"></div></div>
  <div class="row"><div><label>VRRP Priority</label><input id="prio" type="number" value="${c.vrrp_priority||100}"></div><div><label>Mode</label><select id="mode"><option ${c.cluster_mode==='standalone'?'selected':''}>standalone</option><option ${c.cluster_mode==='master'?'selected':''}>master</option><option ${c.cluster_mode==='slave'?'selected':''}>slave</option></select></div></div>
  <label>Master API URL (nur für Slave)</label><input id="master_url" value="${esc(c.master_api_url||'')}">
  <label>Master API Token (nur für Slave)</label><input id="master_token" value="${esc(c.master_api_token||'')}">
  <label>Peer SSH User</label><input id="peer_ssh_user" value="${esc(c.peer_ssh_user||'root')}">
  <details><summary>TLS Zertifikat / Key setzen</summary><textarea id="tls_crt" rows="5" placeholder="-----BEGIN CERTIFICATE-----"></textarea><textarea id="tls_key" rows="5" placeholder="-----BEGIN PRIVATE KEY-----"></textarea></details>
  <details><summary>Queue-Sync SSH Key / known_hosts setzen</summary><textarea id="ssh_private_key" rows="5" placeholder="-----BEGIN OPENSSH PRIVATE KEY-----"></textarea><textarea id="ssh_known_hosts" rows="4" placeholder="peer ssh host key line"></textarea></details>
  <p class="muted">Status: TLS=${c.has_tls?'✔':'✘'} | SSH-Key=${c.has_ssh_key?'✔':'✘'}</p>
  <button id="saveCluster">Cluster Settings speichern</button>
  </div>`;
}

async function mainView(){
  const [rd,dash]=await api('/api/dashboard'); if(rd.status===401){loginView();return}
  const [,conf]=await api('/api/config'); const [,cluster]=await api('/api/cluster/settings');
  app.innerHTML = `<div class="grid"><div class="card"><div class="muted">Processed 24h</div><div class="kpi">${dash.processed_24h}</div></div><div class="card"><div class="muted">Processed 1h</div><div class="kpi">${dash.processed_1h}</div></div><div class="card"><div class="muted">Rejected 16h</div><div class="kpi">${dash.rejected_16h}</div></div><div class="card"><div class="muted">Active Node</div><div class="kpi">${esc(dash.active_node||'n/a')}</div></div></div>
  <div style="margin:10px 0"><button class="secondary" id="logout">Logout</button></div>
  ${clusterForm(cluster)}
  <div class="grid"><div class="card"><h3>Allowed Sender Domains</h3><input id="domain" placeholder="example.com"><button id="addDomain">Hinzufügen</button><ul>${conf.domains.map(d=>`<li>${esc(d.domain)}</li>`).join('')}</ul></div>
  <div class="card"><h3>Sender Route</h3><input id="sd" placeholder="sender-domain.tld"><input id="th" placeholder="target.host"><input id="tp" type="number" value="25"><button id="addRoute">Route speichern</button><ul>${conf.routes.map(r=>`<li>@${esc(r.sender_domain)} → ${esc(r.target_host)}:${r.target_port}</li>`).join('')}</ul></div></div>
  <div class="card"><h3>Apply/Test</h3><button id="test">Konfiguration testen</button><button id="apply">Änderungen übernehmen</button><pre id="out"></pre></div>`;

  logout.onclick=()=>{localStorage.removeItem('token');token='';loginView();};
  saveCluster.onclick=async()=>{
    const body={node_id:node_id.value,node_ip:node_ip.value,peer_node_ip:peer_ip.value,vip_address:vip.value,vrrp_priority:parseInt(prio.value,10),cluster_mode:mode.value,master_api_url:master_url.value||null,master_api_token:master_token.value||null,tls_crt:tls_crt.value||null,tls_key:tls_key.value||null,ssh_private_key:ssh_private_key.value||null,ssh_known_hosts:ssh_known_hosts.value||null,peer_ssh_user:peer_ssh_user.value||'root'};
    const [,d]=await api('/api/cluster/settings',{method:'POST',body:JSON.stringify(body)}); out.textContent=JSON.stringify(d,null,2); mainView();
  };
  addDomain.onclick=async()=>{await api('/api/domains',{method:'POST',body:JSON.stringify({domain:domain.value})}); mainView();};
  addRoute.onclick=async()=>{await api('/api/routes',{method:'POST',body:JSON.stringify({sender_domain:sd.value,target_host:th.value,target_port:parseInt(tp.value,10),tls_mode:'opportunistic',tls_verify:false})}); mainView();};
  test.onclick=async()=>{const [,d]=await api('/api/config/test',{method:'POST',body:'{}'}); out.textContent=JSON.stringify(d,null,2)};
  apply.onclick=async()=>{const [,d]=await api('/api/config/apply',{method:'POST',body:'{}'}); out.textContent=JSON.stringify(d,null,2)};
}

token ? mainView() : loginView();
