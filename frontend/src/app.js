const app = document.getElementById('app');
let token = localStorage.getItem('token') || '';
let state = { tab: 'dashboard', mailRows: [], settingsOpen: false };

const esc = (s='') => String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
async function api(path,opt={}){ opt.headers=Object.assign({},opt.headers||{}, {'Authorization':'Bearer '+token,'content-type':'application/json'}); const r=await fetch(path,opt); let d={}; try{d=await r.json()}catch(_){d={}} return [r,d]; }

function loginView(){
  app.innerHTML = `<div class="card"><h2>Login</h2><input id=u value=admin><input id=p type=password value=Admin123><button id=l>Login</button><pre id=m></pre></div>`;
  document.getElementById('l').onclick = async ()=>{
    const [r,d]=await api('/api/login',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({username:u.value,password:p.value})});
    if(!r.ok){m.textContent=d.detail||'Login fehlgeschlagen'; return;} token=d.token; localStorage.setItem('token',token); renderApp();
  };
}

function shell(content){
  return `<div style="display:flex;gap:12px;align-items:flex-start">
    <div class="card" style="min-width:230px;position:sticky;top:10px">
      <h3>Navigation</h3>
      <button data-tab="dashboard">Dashboard</button>
      <button data-tab="mail">Mail Tracking & Suche</button>
      <button data-tab="config">Routing & Domains</button>
      <button id="openSettings">⚙ Einstellungen</button>
      <button id="logout" style="background:#475569">Logout</button>
    </div>
    <div style="flex:1">${content}</div>
  </div>`;
}

function settingsModal(cluster){
  if(!state.settingsOpen) return '';
  const suggestVip = (cluster.node_ip||'10.0.0.11').split('.').slice(0,3).join('.') + '.50';
  return `<div class="card" style="border:2px solid #60a5fa"><h2>Cluster Einstellungen</h2>
  <p style="opacity:.85">Assistent für Node-Verbindung und VIP</p>
  <div class=row><input id=node_id value="${esc(cluster.node_id||'')}" placeholder="Node ID"><input id=node_ip value="${esc(cluster.node_ip||'')}" placeholder="Node IP"></div>
  <div class=row><input id=peer_node_ip value="${esc(cluster.peer_node_ip||'')}" placeholder="Peer Node IP"><input id=vip_address value="${esc(cluster.vip_address||suggestVip)}" placeholder="VIP Address"></div>
  <div class=row><input id=vrrp_priority type=number value="${cluster.vrrp_priority||100}" placeholder="VRRP Priority"><select id=cluster_mode><option ${cluster.cluster_mode==='standalone'?'selected':''}>standalone</option><option ${cluster.cluster_mode==='master'?'selected':''}>master</option><option ${cluster.cluster_mode==='slave'?'selected':''}>slave</option></select></div>
  <button id=suggestVip>VIP Vorschlag setzen (${suggestVip})</button>
  <button id=testPeer style="background:#0ea5e9">Peer Verbindung testen</button>
  <input id=master_api_url value="${esc(cluster.master_api_url||'')}" placeholder="Master API URL (nur Slave)">
  <input id=master_api_token value="${esc(cluster.master_api_token||'')}" placeholder="Master API Token (nur Slave)">
  <input id=peer_ssh_user value="${esc(cluster.peer_ssh_user||'root')}" placeholder="Peer SSH User">
  <details><summary>TLS / SSH Material (optional)</summary>
  <textarea id=tls_crt placeholder='tls cert'></textarea><textarea id=tls_key placeholder='tls key'></textarea>
  <textarea id=ssh_private_key placeholder='ssh private key'></textarea><textarea id=ssh_known_hosts placeholder='known hosts'></textarea>
  </details>
  <button id=saveCluster>Cluster speichern</button>
  <button id=closeSettings style="background:#334155">Schließen</button>
  <pre id=settingsOut></pre>
  </div>`;
}

function renderMailTab(){
  return `<div class="card"><h2>Mail Tracking & Suche</h2>
  <div class=row><input id=f_sender placeholder="Sender"><input id=f_recipient placeholder="Recipient"></div>
  <div class=row><input id=f_ip placeholder="Client IP"><input id=f_target placeholder="Target"></div>
  <div class=row><input id=f_status placeholder="Status"><input id=f_hours type=number value="24" placeholder="Zeitraum (Stunden)"></div>
  <button id=searchMail>Suchen</button><button id=exportCsv style="background:#16a34a">CSV Export</button>
  <div style="max-height:420px;overflow:auto"><table style="width:100%;font-size:12px"><thead><tr><th>Zeit</th><th>Sender</th><th>Empfänger</th><th>IP</th><th>Status</th><th>Target</th><th>TLS</th></tr></thead>
  <tbody>${state.mailRows.map(r=>`<tr><td>${esc(r.timestamp||'')}</td><td>${esc(r.sender||'')}</td><td>${esc(r.recipient||'')}</td><td>${esc(r.ip||'')}</td><td>${esc(r.status||'')}</td><td>${esc(r.target||'')}</td><td>${r.tls?'yes':'no'}</td></tr>`).join('')}</tbody></table></div>
  </div>`;
}

function renderDashboard(d){
  return `<div class="grid"><div class="card"><h3>Processed 24h</h3>${d.processed_24h||0}</div><div class="card"><h3>Processed 1h</h3>${d.processed_1h||0}</div><div class="card"><h3>Rejected 16h</h3>${d.rejected_16h||0}</div><div class="card"><h3>Active Node</h3>${esc(d.active_node||'')}</div></div>
  <div class="card"><h3>Letzte Rejections</h3><ul>${(d.rejected_last_100||[]).slice(0,20).map(r=>`<li>${esc(r.created_at)} - ${esc(r.sender||'')} -> ${esc(r.recipient||'')} (${esc(r.reason||'')})</li>`).join('')}</ul></div>`;
}

function renderConfigTab(conf){
  return `<div class="grid"><div class="card"><h2>Allowed Domains</h2><input id=domain placeholder='example.com'><button id=addDomain>Domain hinzufügen</button><ul>${(conf.domains||[]).map(d=>`<li>${esc(d.domain)}</li>`).join('')}</ul></div>
  <div class="card"><h2>Sender Routing</h2><input id=sd placeholder='sender-domain'><input id=th placeholder='target host'><input id=tp value='25'><button id=addRoute>Route hinzufügen</button><ul>${(conf.routes||[]).map(r=>`<li>@${esc(r.sender_domain)} → ${esc(r.target_host)}:${r.target_port}</li>`).join('')}</ul>
  <button id=testCfg>Konfiguration testen</button><button id=applyCfg style="background:#16a34a">Änderungen übernehmen</button><pre id=configOut></pre></div></div>`;
}

async function renderApp(){
  const [rd,dash]=await api('/api/dashboard');
  if(rd.status===401){loginView(); return;}
  const [,conf]=await api('/api/config');
  const [,cluster]=await api('/api/cluster/settings');

  let content = state.tab==='dashboard' ? renderDashboard(dash) : state.tab==='mail' ? renderMailTab() : renderConfigTab(conf);
  content += settingsModal(cluster);
  app.innerHTML = shell(content);

  document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{state.tab=b.dataset.tab;renderApp();});
  document.getElementById('logout').onclick=()=>{localStorage.removeItem('token'); token=''; loginView();};
  document.getElementById('openSettings').onclick=()=>{state.settingsOpen=true; renderApp();};

  if(state.tab==='mail'){
    document.getElementById('searchMail').onclick=async()=>{
      const p=new URLSearchParams({sender:f_sender.value,recipient:f_recipient.value,ip:f_ip.value,target:f_target.value,status:f_status.value,hours:f_hours.value||'24'});
      const [,rows]=await api('/api/mail/search?'+p.toString()); state.mailRows=Array.isArray(rows)?rows:[]; renderApp();
    };
    document.getElementById('exportCsv').onclick=()=>window.open('/api/mail/export.csv?hours='+(document.getElementById('f_hours').value||'24'),'_blank');
  }

  if(state.tab==='config'){
    document.getElementById('addDomain').onclick=async()=>{await api('/api/domains',{method:'POST',body:JSON.stringify({domain:domain.value})}); renderApp();};
    document.getElementById('addRoute').onclick=async()=>{await api('/api/routes',{method:'POST',body:JSON.stringify({sender_domain:sd.value,target_host:th.value,target_port:parseInt(tp.value,10),tls_mode:'opportunistic',tls_verify:false})}); renderApp();};
    document.getElementById('testCfg').onclick=async()=>{const [,d]=await api('/api/config/test',{method:'POST',body:'{}'}); configOut.textContent=JSON.stringify(d,null,2)};
    document.getElementById('applyCfg').onclick=async()=>{const [,d]=await api('/api/config/apply',{method:'POST',body:'{}'}); configOut.textContent=JSON.stringify(d,null,2)};
  }

  if(state.settingsOpen){
    document.getElementById('closeSettings').onclick=()=>{state.settingsOpen=false; renderApp();};
    document.getElementById('suggestVip').onclick=()=>{const s=(node_ip.value||'10.0.0.11').split('.').slice(0,3).join('.')+'.50'; vip_address.value=s;};
    document.getElementById('testPeer').onclick=async()=>{const [,d]=await api('/api/cluster/test-peer',{method:'POST',body:'{}'}); settingsOut.textContent=JSON.stringify(d,null,2)};
    document.getElementById('saveCluster').onclick=async()=>{
      const body={node_id:node_id.value,node_ip:node_ip.value,peer_node_ip:peer_node_ip.value,vip_address:vip_address.value,vrrp_priority:parseInt(vrrp_priority.value,10),cluster_mode:cluster_mode.value,master_api_url:master_api_url.value||null,master_api_token:master_api_token.value||null,peer_ssh_user:peer_ssh_user.value||'root',tls_crt:tls_crt.value||null,tls_key:tls_key.value||null,ssh_private_key:ssh_private_key.value||null,ssh_known_hosts:ssh_known_hosts.value||null};
      const [,d]=await api('/api/cluster/settings',{method:'POST',body:JSON.stringify(body)}); settingsOut.textContent=JSON.stringify(d,null,2);
    };
  }
}

token ? renderApp() : loginView();
