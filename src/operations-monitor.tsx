import { useEffect, useState } from 'react';
import { Activity, AlertCircle, Monitor, RefreshCw, Signal, WifiOff } from 'lucide-react';
import './operations-monitor.css';

type Loop = { agent_id: string; name: string; role: string; initials: string; enabled: boolean; interval_seconds: number; last_started_at: string | null; last_run_id: string | null; last_error: string | null };
type MonitorEvent = { id: number; type: string; at: string; data: Record<string, unknown> };
type Operations = { loops: Loop[]; events: MonitorEvent[] };

async function fetchOperations(profileId: string): Promise<Operations> {
  const response = await fetch(`/api/profiles/${encodeURIComponent(profileId)}/operations`);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || 'Could not load operations monitor.');
  return body as Operations;
}

function relativeTime(value: string | null) {
  if (!value) return 'Not observed';
  const seconds = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) return 'Just now';
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  return `${Math.round(seconds / 3600)}h ago`;
}

export function OperationsMonitor({ profileId, profileName }: { profileId: string; profileName: string }) {
  const [state, setState] = useState<Operations | null>(null);
  const [error, setError] = useState('');
  const refresh = async () => { try { setError(''); setState(await fetchOperations(profileId)); } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not load operations monitor.'); } };
  useEffect(() => { void refresh(); const timer = window.setInterval(() => void refresh(), 10_000); return () => window.clearInterval(timer); }, [profileId]);
  return <div className="page operations-monitor"><header className="page-header"><div><h1>Operations monitor</h1><p>Verified laptop-side loop and run state for {profileName}. This is not desktop screen capture.</p></div><div className="page-actions"><button className="button button-quiet" onClick={() => void refresh()}><RefreshCw size={14} /> Refresh</button></div></header>{error && <div className="form-error" role="alert">{error}</div>}<section className="monitor-stage" aria-label="Agent operation cells"><header><div><Signal size={15} /><span>Live loop telemetry</span></div><small>Refreshes every 10 seconds</small></header>{!state ? <div className="monitor-loading">Reading local runtime state…</div> : state.loops.length ? <div className="monitor-grid">{state.loops.map(loop => <article className={`monitor-cell ${loop.last_error ? 'blocked' : loop.last_run_id ? 'observed' : ''}`} key={loop.agent_id}><header><span className="monitor-agent-mark">{loop.initials || loop.name.slice(0, 2).toUpperCase()}</span><div><strong>{loop.name}</strong><small>{loop.role || 'General agent'}</small></div><span className={`monitor-state ${loop.last_error ? 'blocked' : loop.last_run_id ? 'observed' : 'idle'}`}>{loop.last_error ? 'Blocked' : loop.last_run_id ? 'Observed' : loop.enabled ? 'Waiting' : 'Paused'}</span></header><div className="monitor-surface"><Monitor size={24} /><p>{loop.last_error || (loop.last_run_id ? `Run ${loop.last_run_id}` : 'No agent surface has been observed yet.')}</p></div><footer><span><Activity size={13} /> {relativeTime(loop.last_started_at)}</span><span>Every {Math.round(loop.interval_seconds / 60)}m</span></footer></article>)}</div> : <div className="monitor-empty"><WifiOff size={22} /><div><strong>No agent loops are configured</strong><p>Create an agent with looping enabled to observe its actual run lifecycle here.</p></div></div>}</section>{state && <section className="monitor-events"><header><h2>Recent events</h2><span>{state.events.length} recorded</span></header>{state.events.length ? <div>{state.events.slice(0, 8).map(event => <article key={event.id}><span className="status-dot live" /><strong>{event.type}</strong><time>{relativeTime(event.at)}</time></article>)}</div> : <div className="monitor-empty compact"><AlertCircle size={18} /><p>Agent loop and run events will appear after the laptop runtime records them.</p></div>}</section>}</div>;
}
