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
  app.innerHTML = `<button id=logout>Logout</button>
  <h2>Dashboard</h2>
  <p>Processed 24h: ${dash.processed_24h} | Processed 1h: ${dash.processed_1h} | Rejected 16h: ${dash.rejected_16h} | Active Node: ${dash.active_node}</p>
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
