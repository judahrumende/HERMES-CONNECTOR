import { useEffect, useState } from 'react';
import { AlertCircle, ExternalLink, FileText, GitBranch, RefreshCw, ShieldCheck } from 'lucide-react';
import './graphify-page.css';

type GraphifyState = {
  profile_id: string;
  profile_name: string;
  vault_configured: boolean;
  vault_available: boolean;
  vault_path: string;
  graph_available: boolean;
  graph_html_available: boolean;
  report_available: boolean;
  issue: string | null;
};

type ComposioState = { configured: boolean; verified: boolean; provider: string; scope: string; detail: string };

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...options });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
  return data as T;
}

export function GraphifyPage({ profileId, profileName }: { profileId: string; profileName: string }) {
  const [state, setState] = useState<GraphifyState | null>(null);
  const [error, setError] = useState('');
  const refresh = async () => {
    if (!profileId) return;
    setError('');
    try { setState(await request<GraphifyState>(`/api/profiles/${encodeURIComponent(profileId)}/graphify`)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not inspect this profile vault.'); }
  };
  useEffect(() => { void refresh(); }, [profileId]);

  const noOutput = !state?.graph_available;
  return <div className="page graphify-page">
    <header className="page-header"><div><div className="eyebrow"><GitBranch size={13} /> Profile graph</div><h1>Graphify</h1><p>Explore the real Graphify output for {profileName}'s configured Obsidian vault.</p></div><div className="page-actions"><button className="button button-quiet" onClick={() => void refresh()}><RefreshCw size={14} /> Refresh</button><a className="button button-quiet" href="https://github.com/Graphify-Labs/graphify" target="_blank" rel="noreferrer">Graphify docs <ExternalLink size={13} /></a></div></header>
    {error && <div className="form-error" role="alert">{error}</div>}
    {!state ? <section className="graphify-loading">Reading profile vault configuration…</section> : <>
      <section className="graphify-status-card">
        <div className="graphify-status-icon"><GitBranch size={20} /></div>
        <div><span className={`graphify-state ${state.graph_html_available ? 'ready' : ''}`}>{state.graph_html_available ? 'Graph ready' : state.vault_available ? 'Vault connected' : 'Needs vault'}</span><h2>{state.graph_html_available ? 'Interactive graph is ready to explore.' : state.issue || 'Graphify output is not available.'}</h2><p>{state.vault_available ? state.vault_path : 'Set an existing Obsidian vault path when creating the profile. OrbityLabs does not scan your computer for one.'}</p></div>
        {state.report_available && <a className="button button-quiet" href={`/api/profiles/${encodeURIComponent(profileId)}/graphify/report`} target="_blank" rel="noreferrer"><FileText size={14} /> Open report</a>}
      </section>
      {noOutput && <section className="graphify-guide"><div><AlertCircle size={18} /><div><h2>Generate the graph inside this vault</h2><p>Graphify must be installed and run in this profile’s vault. Once it has created <code>graphify-out/graph.html</code>, refresh this page to display that real output.</p></div></div><pre><code>uv tool install graphifyy{state.vault_available ? `\ncd ${JSON.stringify(state.vault_path)}\ngraphify .` : ''}</code></pre><small>Graphify is not bundled with OrbityLabs, and this page does not fabricate a graph when no output exists.</small></section>}
      {state.graph_html_available && <section className="graphify-frame-wrap"><header><div><ShieldCheck size={15} /><span>Profile-scoped Graphify output</span></div><small>Loaded from this profile’s vault only</small></header><iframe title={`${profileName} Graphify graph`} src={`/api/profiles/${encodeURIComponent(profileId)}/graphify/view`} sandbox="allow-scripts" referrerPolicy="no-referrer" /></section>}
    </>}
  </div>;
}

export function ConnectorsPage() {
  const [state, setState] = useState<ComposioState | null>(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState('');
  const load = async (verify = false) => {
    setChecking(true); setError('');
    try { setState(await request<ComposioState>(verify ? '/api/connectors/composio/verify' : '/api/connectors/composio', verify ? { method: 'POST' } : undefined)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not check Composio.'); }
    finally { setChecking(false); }
  };
  useEffect(() => { void load(); }, []);
  return <div className="page connectors-page"><header className="page-header"><div><div className="eyebrow"><ShieldCheck size={13} /> Integrations</div><h1>Connectors</h1><p>Connect external services through Composio while secrets remain in the local desktop server.</p></div></header><section className="connector-card"><div className="connector-card-top"><div className="connector-logo">C</div><div><span className={`graphify-state ${state?.verified ? 'ready' : ''}`}>{state?.verified ? 'Verified' : state?.configured ? 'Configured' : 'Not configured'}</span><h2>Composio</h2><p>{state?.detail || 'Checking server configuration…'}</p></div></div><div className="connector-boundary"><ShieldCheck size={16} /><p>Composio credentials are read by the desktop server only. They are never sent to this browser, attached to an agent prompt, or shared across profiles automatically.</p></div><footer><button className="button button-primary" disabled={checking || !state?.configured} onClick={() => void load(true)}>{checking ? 'Checking…' : 'Verify Composio key'}</button><a className="button button-quiet" href="https://docs.composio.dev/docs/quickstart" target="_blank" rel="noreferrer">Set up Composio <ExternalLink size={13} /></a></footer>{!state?.configured && <small className="connector-help">Add <code>COMPOSIO_API_KEY</code> to the OrbityLabs desktop server environment and restart the app. Account authorization is a separate, operator-approved Connect Link flow per profile.</small>}{error && <div className="form-error" role="alert">{error}</div>}</section><section className="desktop-boundary"><GitBranch size={18} /><div><h2>Desktop capability boundary</h2><p>Profile vaults can be read for Graphify only when you explicitly configure their path. Desktop apps, files outside a configured vault, and accessibility automation are not exposed to agents by default. Adding a tool requires a specific, logged capability and operator authorization.</p></div></section></div>;
}
