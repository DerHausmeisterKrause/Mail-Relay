const app = document.getElementById('app');
let token = localStorage.getItem('token') || '';

function renderLogin() {
  app.innerHTML = `<h2>Login</h2><input id=u placeholder=username value=admin><input id=p type=password placeholder=password value=Admin123><button id=l>Login</button><p id=m></p>`;
  document.getElementById('l').onclick = async () => {
    const username = document.getElementById('u').value;
    const password = document.getElementById('p').value;
    const r = await fetch('/api/login',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({username,password})});
    const d = await r.json();
    if(!r.ok){document.getElementById('m').textContent=d.detail||'failed';return;}
    token = d.token; localStorage.setItem('token', token); renderMain();
  }
}

async function api(path, options={}) {
  options.headers = Object.assign({}, options.headers||{}, {'Authorization':'Bearer '+token, 'content-type':'application/json'});
  const r = await fetch(path, options);
  return [r, await r.json()];
}

async function renderMain(){
  const [rd, dash] = await api('/api/dashboard');
  if(rd.status===401){renderLogin(); return;}
  const [, conf] = await api('/api/config');
  const [, cluster] = await api('/api/cluster/settings');
  app.innerHTML = `<button id=logout>Logout</button>
  <h2>Dashboard</h2>
  <p>Processed 24h: ${dash.processed_24h} | Processed 1h: ${dash.processed_1h} | Rejected 16h: ${dash.rejected_16h} | Active Node: ${dash.active_node}</p>

  <h3>Cluster / Node Settings (via GUI)</h3>
  <label>Node ID <input id=node_id value='${cluster.node_id||''}'></label>
  <label>Node IP <input id=node_ip value='${cluster.node_ip||''}'></label>
  <label>Peer Node IP <input id=peer_ip value='${cluster.peer_node_ip||''}'></label>
  <label>VIP Address <input id=vip value='${cluster.vip_address||''}'></label>
  <label>VRRP Priority <input id=prio type=number value='${cluster.vrrp_priority||100}'></label>
  <label>Cluster Mode
    <select id=mode>
      <option value='standalone' ${cluster.cluster_mode==='standalone'?'selected':''}>standalone</option>
      <option value='master' ${cluster.cluster_mode==='master'?'selected':''}>master</option>
      <option value='slave' ${cluster.cluster_mode==='slave'?'selected':''}>slave</option>
    </select>
  </label>
  <label>Master API URL <input id=master_url value='${cluster.master_api_url||''}'></label>
  <label>Master API Token <input id=master_token value='${cluster.master_api_token||''}'></label>
  <details><summary>TLS Zertifikate (optional hier setzen/aktualisieren)</summary>
    <textarea id=tls_crt rows=6 cols=80 placeholder='-----BEGIN CERTIFICATE-----'></textarea>
    <textarea id=tls_key rows=6 cols=80 placeholder='-----BEGIN PRIVATE KEY-----'></textarea>
  </details>
  <button id=saveCluster>Cluster Settings speichern</button>
  <p><small>Hinweis: Nach Änderung von VIP/VRRP/Peer ggf. keepalived + queue-sync Container neu starten.</small></p>

  <h3>Allowed Domains</h3><input id=domain placeholder='example.com'><button id=addDomain>Add</button>
  <ul>${conf.domains.map(d=>`<li>${d.domain}</li>`).join('')}</ul>
  <h3>Sender Routes</h3>
  <input id=sd placeholder='sender domain'> <input id=th placeholder='target host'> <input id=tp placeholder='port' value='25'>
  <button id=addRoute>Add Route</button>
  <ul>${conf.routes.map(r=>`<li>@${r.sender_domain} -> ${r.target_host}:${r.target_port}</li>`).join('')}</ul>
  <button id=test>Konfiguration testen</button> <button id=apply>Änderungen übernehmen</button>
  <pre id=out></pre>
  `;
  document.getElementById('logout').onclick=()=>{localStorage.removeItem('token');token='';renderLogin();};
  document.getElementById('saveCluster').onclick=async()=>{
    const body={
      node_id:document.getElementById('node_id').value,
      node_ip:document.getElementById('node_ip').value,
      peer_node_ip:document.getElementById('peer_ip').value,
      vip_address:document.getElementById('vip').value,
      vrrp_priority:parseInt(document.getElementById('prio').value,10),
      cluster_mode:document.getElementById('mode').value,
      master_api_url:document.getElementById('master_url').value||null,
      master_api_token:document.getElementById('master_token').value||null,
      tls_crt:document.getElementById('tls_crt').value||null,
      tls_key:document.getElementById('tls_key').value||null,
    };
    const [,d]=await api('/api/cluster/settings',{method:'POST',body:JSON.stringify(body)});
    document.getElementById('out').textContent=JSON.stringify(d,null,2);
  };
  document.getElementById('addDomain').onclick=async()=>{const domain=document.getElementById('domain').value;await api('/api/domains',{method:'POST',body:JSON.stringify({domain})});renderMain();};
  document.getElementById('addRoute').onclick=async()=>{
    const sender_domain=document.getElementById('sd').value;
    const target_host=document.getElementById('th').value;
    const target_port=parseInt(document.getElementById('tp').value,10);
    await api('/api/routes',{method:'POST',body:JSON.stringify({sender_domain,target_host,target_port,tls_mode:'opportunistic',tls_verify:false})});
    renderMain();
  };
  document.getElementById('test').onclick=async()=>{const [,d]=await api('/api/config/test',{method:'POST',body:'{}'});document.getElementById('out').textContent=JSON.stringify(d,null,2)};
  document.getElementById('apply').onclick=async()=>{const [,d]=await api('/api/config/apply',{method:'POST',body:'{}'});document.getElementById('out').textContent=JSON.stringify(d,null,2)};
}

if(token) renderMain(); else renderLogin();
