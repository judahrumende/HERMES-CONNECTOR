import React, { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { Html5QrcodeScanner } from 'html5-qrcode';
import type { Session } from '@supabase/supabase-js';
import { supabase, supabaseAuthConfigured } from './lib/supabase';
import { AgentProviderManager } from './agent-provider-manager';
import { ConnectorsPage, GraphifyPage } from './graphify-page';
import { OperationsMonitor } from './operations-monitor';
import { SkillsPage } from './skills-page';
import {
  Activity, AlertCircle, ArrowRight, Bell, Bot, Check, ChevronLeft, ChevronRight,
  Camera, Circle, CornerDownLeft, Database, Download, FileJson, Image as ImageIcon, Inbox, LayoutDashboard, ListFilter,
  ListChecks, Menu, MessageSquare, Mic, Minimize2, Network, Paperclip, Pencil, Plus, RefreshCw, Search, Send,
  Settings, ShieldCheck, Sparkles, Stethoscope, Timer, Upload, UserPlus, Users, Webhook, X, Zap, Copy as CopyIcon, ScanLine, Smartphone, Laptop, Layers, GitBranch, Plug, Square, Wrench, Monitor,
} from 'lucide-react';
import './convos-app.css';
import './branding.css';
import './profile.css';
import { createGroupRun, exportApprovals, exportProfile, fetchGlobalContext, importProfile, searchMessages, stopRun, useAgentNotes, useDoctorReport, useMessagePreviews, useProfileAgents, useProfileApprovals, useProfileMessages, useProfileModelRoutes, useProfilePolicy, useProfileRuns, useProfileSkills, useProfileSources, useProfileTasks, useProfileToolEvents, useProfiles, useScheduledDirectives, useVaultDiff, webhookUrl } from './lib/profile-api';
import type { AgentRuntime, Approval, ApprovalMode, DoctorCheck, GroupRunResult, Role, Run, ScheduledDirective, Source, Status, Task, ToolEvent, VaultFile, WorkspaceProfile } from './lib/profile-api';

type View = 'overview' | 'setup' | 'messages' | 'work' | 'agents' | 'skills' | 'knowledge' | 'approvals' | 'settings' | 'pairing' | 'profiles' | 'global' | 'graphify' | 'connectors' | 'doctor' | 'timeline' | 'schedule' | 'operations';
type Kind = 'directive' | 'task' | 'role' | 'group' | 'source' | 'connection' | 'job' | null;
type Gateway = { status: 'loading' | 'bridge_offline' | 'not_configured' | 'unknown' | 'offline' | 'online'; base_url?: string | null; checked_at?: string | null; models?: unknown; jobs?: unknown; error?: string | null };
type Event = { type: string; at?: string; data?: Record<string, unknown> };

function scopedStorageKey(key: string, profileId: string) { return `${key}.${profileId || 'unassigned'}`; }
type ChatMessage = { text: string; direction: 'outgoing' | 'incoming'; status?: 'sent' | 'working' };

function normalizeChatMessage(value: unknown): ChatMessage | null {
  if (typeof value === 'string') return { text: value, direction: 'outgoing', status: 'sent' };
  if (!value || typeof value !== 'object') return null;
  const message = value as Partial<ChatMessage>;
  return typeof message.text === 'string' && (message.direction === 'incoming' || message.direction === 'outgoing')
    ? { text: message.text, direction: message.direction, status: message.status }
    : null;
}

function extractResponseText(value: unknown, depth = 0): string | null {
  if (depth > 4 || value === null || value === undefined) return null;
  if (typeof value === 'string') return value.trim() || null;
  if (Array.isArray(value)) {
    const parts = value.map(item => extractResponseText(item, depth + 1)).filter(Boolean) as string[];
    return parts.length ? parts.join('\n') : null;
  }
  if (typeof value !== 'object') return null;
  const record = value as Record<string, unknown>;
  for (const key of ['output', 'response', 'answer', 'reply', 'message', 'content', 'text', 'final']) {
    const result = extractResponseText(record[key], depth + 1);
    if (result) return result;
  }
  return null;
}

const nav: Array<{ id: View; label: string; icon: React.ElementType }> = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard }, { id: 'profiles', label: 'Profiles', icon: Layers }, { id: 'global', label: 'All profiles', icon: MessageSquare }, { id: 'setup', label: 'Steps to do', icon: ListChecks }, { id: 'messages', label: 'Messages', icon: MessageSquare },
  { id: 'work', label: 'Work', icon: Inbox }, { id: 'agents', label: 'Agents', icon: Bot },
  { id: 'skills', label: 'Skills', icon: Sparkles }, { id: 'knowledge', label: 'Knowledge', icon: Database }, { id: 'graphify', label: 'Graphify', icon: GitBranch }, { id: 'connectors', label: 'Connectors', icon: Plug }, { id: 'operations', label: 'Operations', icon: Monitor }, { id: 'approvals', label: 'Approvals', icon: ShieldCheck }, { id: 'timeline', label: 'Run Timeline', icon: Activity }, { id: 'schedule', label: 'Schedule', icon: Timer }, { id: 'pairing', label: 'Pairing', icon: ScanLine }, { id: 'doctor', label: 'Doctor', icon: Stethoscope },
];

function useStored<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(() => { try { return JSON.parse(localStorage.getItem(key) || '') as T; } catch { return initial; } });
  const activeKey = useRef(key), skipWrite = useRef(false);
  useEffect(() => { if (activeKey.current === key) return; activeKey.current = key; skipWrite.current = true; try { setValue(JSON.parse(localStorage.getItem(key) || '') as T); } catch { setValue(initial); } }, [key]);
  useEffect(() => { if (skipWrite.current) { skipWrite.current = false; return; } localStorage.setItem(key, JSON.stringify(value)); }, [key, value]);
  return [value, setValue] as const;
}

function useHermes() {
  const [status, setStatus] = useState<Gateway>({ status: 'loading' });
  const [events, setEvents] = useState<Event[]>([]);
  const request = async (url: string, options?: RequestInit) => {
    const response = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...options });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
    return body;
  };
  const refresh = async () => { try { setStatus(await request('/api/hermes/refresh', { method: 'POST' })); } catch { setStatus(s => ({ ...s, status: 'bridge_offline', error: 'Start the Hermes Jarvis server to enable connections.' })); } };
  useEffect(() => {
    request('/api/hermes/status').then(setStatus).catch(() => setStatus({ status: 'bridge_offline', error: 'Start the Hermes Jarvis server to enable connections.' }));
    const socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/live`);
    socket.onmessage = e => { try { const item = JSON.parse(e.data); setEvents(old => [item, ...old].slice(0, 100)); if (item.type.startsWith('connection.')) setStatus(item.data); } catch { /* upstream data was malformed */ } };
    return () => socket.close();
  }, []);
  return { status, events, refresh,
    configure: async (base_url: string) => { const value = await request('/api/hermes/connection', { method: 'PUT', body: JSON.stringify({ base_url }) }); setStatus(value); if (value.status === 'online') localStorage.setItem('orbitylabs.hermes.setup.pending', '1'); },
    run: (input: string, session_id: string, runtime?: AgentRuntime) => request('/api/hermes/runs', { method: 'POST', body: JSON.stringify({ payload: { input, session_id, ...(runtime?.provider ? { provider: runtime.provider } : {}), ...(runtime?.model ? { model: runtime.model } : {}) } }) }),
    job: (payload: Record<string, string>) => request('/api/hermes/jobs', { method: 'POST', body: JSON.stringify({ payload }) }),
  };
}

export default function FinishedApp({ landing }: { landing: (onEnter: () => void) => React.ReactNode }) {
  const isDesktop = typeof navigator !== 'undefined' && navigator.userAgent.includes('Electron');
  const [inside, setInside] = useStored('hermes.inside.v2', isDesktop);
  const [showSetupCelebration, setShowSetupCelebration] = useState(() => { const pending = localStorage.getItem('orbitylabs.hermes.setup.pending') === '1'; if (pending) localStorage.removeItem('orbitylabs.hermes.setup.pending'); return pending; });
  const [session, setSession] = useState<Session | null>(null);
  const [authReady, setAuthReady] = useState(isDesktop || !supabaseAuthConfigured);
  const pairing = new URLSearchParams(location.search);
  const isPhone = matchMedia('(max-width: 720px)').matches;
  const paired = Boolean(localStorage.getItem('hermes.mobile.pairing'));
  useEffect(() => { if (!showSetupCelebration) return; const timer = window.setTimeout(() => setShowSetupCelebration(false), 2000); return () => window.clearTimeout(timer); }, [showSetupCelebration]);
  useEffect(() => {
    if (!supabase) return;
    let active = true;
    supabase.auth.getSession().then(({ data }) => { if (active) { setSession(data.session); setAuthReady(true); } });
    const { data: listener } = supabase.auth.onAuthStateChange((_event, nextSession) => setSession(nextSession));
    return () => { active = false; listener.subscription.unsubscribe(); };
  }, []);
  if (isPhone && (pairing.has('pair') || pairing.has('token') || !paired)) return <MobilePairing />;
  if (showSetupCelebration) return <SetupCelebration />;
  if (!inside && !isDesktop && !(isPhone && paired)) return <>{landing(() => setInside(true))}</>;
  if (!isDesktop && !supabaseAuthConfigured) return <AuthScreen configured={false} />;
  if (!authReady) return <div className="auth-loading" role="status">Checking your session...</div>;
  if (!isDesktop && !session) return <AuthScreen configured />;
  return <Centre onExit={() => setInside(false)} mobileCompanion={isPhone && paired} />;
}

function SetupCelebration() {
  return <main className="setup-celebration" role="status" aria-live="polite"><div className="celebration-orbit"><span className="brand-orb" /><i /><i /><i /></div><span className="auth-eyebrow">CONNECTION VERIFIED</span><h1>OrbityLabs is ready.</h1><p>Your Hermes gateway is connected and the command centre is set up.</p></main>;
}

function ProfilePanel({ profileId, gateway, close, onExit }: { profileId: string; gateway: Gateway; close: () => void; onExit: () => void }) {
  const connected = gateway.status === 'online';
  const signOut = async () => { if (supabase) await supabase.auth.signOut(); close(); };
  const [importing, setImporting] = useState(false), [importError, setImportError] = useState('');
  const fileRef = React.useRef<HTMLInputElement>(null);
  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]; if (!file) return;
    setImporting(true); setImportError('');
    try { const result = await importProfile(file); alert(`Imported profile: ${result.name}`); close(); }
    catch (err) { setImportError(err instanceof Error ? err.message : 'Import failed.'); }
    finally { setImporting(false); }
  };
  const hookUrl = profileId && profileId !== 'unassigned' ? webhookUrl(profileId) : null;
  return <div className="profile-backdrop" onMouseDown={close}><section className="profile-panel" role="dialog" aria-modal="true" aria-labelledby="profile-title" onMouseDown={event => event.stopPropagation()}><header><div><span className="profile-avatar">JR</span><div><h2 id="profile-title">Judah Rumende</h2><p>Operator account</p></div></div><button className="icon-button" onClick={close} aria-label="Close profile"><X size={17} /></button></header><div className="profile-connection"><span className={`status-dot ${connected ? 'live' : 'idle'}`} /><div><strong>{connected ? 'Hermes connected' : 'Hermes not connected'}</strong><small>{connected ? gateway.base_url || 'Verified gateway' : 'Connect a gateway to enable live organisation work.'}</small></div></div>
    {hookUrl && <div className="profile-webhook"><Webhook size={13} /><span>Webhook</span><code className="mono webhook-url">{hookUrl}</code><button className="icon-button" onClick={() => navigator.clipboard.writeText(hookUrl)} title="Copy webhook URL"><CopyIcon size={13} /></button></div>}
    <div className="profile-actions">
      {profileId && profileId !== 'unassigned' && <><button className="button button-outline" onClick={() => exportProfile(profileId)}><Download size={13} /> Export profile</button><button className="button button-outline" onClick={() => fileRef.current?.click()}><Upload size={13} /> {importing ? 'Importing...' : 'Import profile'}</button><input ref={fileRef} type="file" accept=".json" onChange={handleImport} style={{ display: 'none' }} /></>}
      {importError && <p className="form-error">{importError}</p>}
      <button className="button button-outline" onClick={onExit}>Return to company site</button>
      {supabase && <button className="button button-secondary" onClick={signOut}>Sign out</button>}
    </div>
  </section></div>;
}

function AuthScreen({ configured = true }: { configured?: boolean }) {
  const [mode, setMode] = useState<'signin' | 'signup'>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!supabase) return;
    setBusy(true); setError(''); setMessage('');
    const result = mode === 'signin'
      ? await supabase.auth.signInWithPassword({ email: email.trim(), password })
      : await supabase.auth.signUp({ email: email.trim(), password });
    if (result.error) setError(result.error.message);
    else if (mode === 'signup' && !result.data.session) setMessage('Check your email to confirm your account, then return here to sign in.');
    setBusy(false);
  };
  const oauth = async (provider: 'google') => {
    if (!supabase) return;
    setBusy(true); setError('');
    const { error: oauthError } = await supabase.auth.signInWithOAuth({ provider, options: { redirectTo: window.location.origin } });
    if (oauthError) { setError(oauthError.message); setBusy(false); }
  };
  return <main className="auth-page"><section className="auth-card" aria-labelledby="auth-title"><div className="auth-brand"><span className="brand-orb" /><div><strong>OrbityLabs</strong><small>COMMAND CENTRE</small></div></div><div className="auth-copy"><span className="auth-eyebrow">OPERATOR ACCESS</span><h1 id="auth-title">Welcome back.</h1><p>Sign in to direct your organisation, review decisions, and keep authority with the operator.</p></div>{!configured ? <div className="auth-config-error" role="alert"><strong>Authentication is not configured.</strong><span>Add <code>VITE_SUPABASE_URL</code> and <code>VITE_SUPABASE_PUBLISHABLE_KEY</code> to your local or Vercel environment variables.</span></div> : <><div className="auth-socials"><button className="auth-provider" onClick={() => oauth('google')} disabled={busy}><span className="provider-letter google-letter">G</span> Continue with Google</button></div><div className="auth-divider"><span>or use email</span></div><form className="auth-form" onSubmit={submit}><label>Email address<input type="email" autoComplete="email" required value={email} onChange={event => setEmail(event.target.value)} placeholder="you@company.com" /></label><label>Password<input type="password" autoComplete={mode === 'signin' ? 'current-password' : 'new-password'} minLength={8} required value={password} onChange={event => setPassword(event.target.value)} placeholder="8 characters minimum" /></label>{error && <div className="auth-error" role="alert">{error}</div>}{message && <div className="auth-success" role="status">{message}</div>}<button className="button button-primary auth-submit" disabled={busy}>{busy ? 'Working...' : mode === 'signin' ? 'Sign in' : 'Create account'} <ArrowRight size={14} /></button></form><button className="auth-mode" onClick={() => { setMode(mode === 'signin' ? 'signup' : 'signin'); setError(''); setMessage(''); }}>{mode === 'signin' ? 'New to OrbityLabs? Create an account' : 'Already have an account? Sign in'}</button></>}<p className="auth-privacy">By continuing, you agree to your organisation's access policy. Sessions are managed by Supabase Auth.</p></section></main>;
}

function Centre({ onExit, mobileCompanion = false }: { onExit: () => void; mobileCompanion?: boolean }) {
  const hermes = useHermes();
  const [view, setView] = useStored<View>('hermes.view', 'overview');
  const { profiles, createProfile: createProfileRemote } = useProfiles();
  const [activeProfile, setActiveProfile] = useStored<string>('hermes.active.profile', '');
  const profileKey = activeProfile || 'unassigned';
  const [activeRole, setActiveRole] = useStored(scopedStorageKey('hermes.active.role', profileKey), '');
  const { tasks, createTask, toggleTask, deleteTask } = useProfileTasks(activeProfile);
  const { agents: roles, createAgent } = useProfileAgents(activeProfile);
  const { sources, createSource } = useProfileSources(activeProfile);
  const [setupDone, setSetupDone] = useStored<string[]>(scopedStorageKey('hermes.setup.completed', profileKey), []);
  const { autonomy: approvalMode, setAutonomy: setApprovalMode } = useProfilePolicy(activeProfile);
  const { routes: agentRuntimes, setRoute: setAgentRoute } = useProfileModelRoutes(activeProfile);
  const { skills, agentSkills, createSkill } = useProfileSkills(activeProfile);
  const [dialog, setDialog] = useState<Kind>(null), [search, setSearch] = useState(false), [notes, setNotes] = useState(false), [agent, setAgent] = useState(false), [profile, setProfile] = useState(false), [menu, setMenu] = useState(false), [workspaceMenu, setWorkspaceMenu] = useState(false);
  useEffect(() => { if (mobileCompanion) setView('messages'); }, [mobileCompanion, setView]);
  useEffect(() => { const interceptProfile = (event: MouseEvent) => { const target = event.target as HTMLElement; if (target.closest('.profile-switcher, .topbar-actions .identity-avatar')) { event.preventDefault(); event.stopPropagation(); setProfile(true); } }; addEventListener('click', interceptProfile, true); return () => removeEventListener('click', interceptProfile, true); }, []);
  useEffect(() => { const fn = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setSearch(true); } if (e.key === 'Escape') { setSearch(false); setNotes(false); setDialog(null); } }; addEventListener('keydown', fn); return () => removeEventListener('keydown', fn); }, []);
  const goSettings = () => setView('settings');
  const openThread = (id: string) => { setActiveRole(id); setView('messages'); setMenu(false); };
  const createProfile = (name: string, kind: string, context: string, vaultPath: string) => { void createProfileRemote(name, kind || 'Workspace', context, vaultPath).then(created => { setActiveProfile(created.id); setView('overview'); setWorkspaceMenu(false); }).catch(() => undefined); };
  const currentProfile = profiles.find(item => item.id === activeProfile);
  const createRole = (role: Role) => { if (!currentProfile) return; void createAgent(role.name, role.role, role.initials).then(created => { if (hermes.status.status === 'online' && !created.role.startsWith('Group chat')) void hermes.run(`Create this agent only inside the OrbityLabs profile named "${currentProfile.name}". Profile context: ${currentProfile.context || 'No context supplied'}. Obsidian vault: ${currentProfile.vault_path || 'Not configured'}. Agent name: ${created.name}. Agent responsibility: ${created.role}. Required skill sources: Steel Browser (https://github.com/steel-dev/steel-browser) and AgenticMail (https://github.com/agenticmail/agenticmail). Record them as source references for this agent. Do not download, execute, configure credentials for, or grant permissions to either source unless the operator explicitly asks and the relevant provider is configured. Do not access another profile unless the operator explicitly asks. Using only tools and providers that are actually configured, provision a dedicated email identity and phone number for this agent. Check provider availability first. Ask for approval before any external, paid, irreversible, or administrator action. Never invent an address, number, provider result, credential, or completion. If provisioning is unavailable, report exactly what is missing and leave the identity state as Not configured. Never print passwords, API keys, recovery codes, or other secrets. Return completed, blocked, and awaiting-approval items.`, `profile-${currentProfile.id}-agent-${created.id}`).catch(() => undefined); }).catch(() => undefined); };
  return <div className={`command-app convos-command ${mobileCompanion ? 'mobile-companion' : ''} ${view === 'overview' ? 'dashboard-active' : ''}`}><aside className={`app-sidebar convos-sidebar ${menu ? 'mobile-open' : ''}`}><header className="convos-brand"><button className="brand-button" onClick={() => setView('overview')}><span className="brand-orb" /><strong>OrbityLabs</strong></button><button className="icon-button" aria-label="Close navigation" onClick={() => setMenu(false)}><X size={20} /></button></header><button className="command-search" onClick={() => setSearch(true)}><Search size={17} /><span>Search OrbityLabs</span><kbd>⌘ K</kbd></button><button className="workspace-picker" onClick={() => setWorkspaceMenu(value => !value)} aria-expanded={workspaceMenu}><span className="workspace-mark">{profiles.find(item => item.id === activeProfile)?.name.slice(0, 1).toUpperCase() || '＋'}</span><span><small>Active profile</small><strong>{profiles.find(item => item.id === activeProfile)?.name || 'Choose a profile'}</strong></span><ChevronRight size={15} /></button>{workspaceMenu && <WorkspaceMenu profiles={profiles} activeProfile={activeProfile} select={id => { setActiveProfile(id); setWorkspaceMenu(false); setView('overview'); }} create={createProfile} />}<nav aria-label="Command centre"><span className="nav-label">Command centre</span>{nav.map(item => <Nav key={item.id} {...item} active={view === item.id} onClick={() => { setView(item.id); setMenu(false); }} />)}<span className="nav-label nav-label-spaced">System</span><Nav id="settings" label="Settings" icon={Settings} active={view === 'settings'} onClick={() => { goSettings(); setMenu(false); }} /></nav><div className="sidebar-spacer" /><button className="sidebar-connection" onClick={goSettings}><span className={`status-dot ${tone(hermes.status)}`} /><div><strong>{statusText(hermes.status)}</strong><small>{hermes.status.base_url || 'Local-only workspace'}</small></div></button><button className="new-convo-button" onClick={() => setDialog('directive')}><Pencil size={17} /> New directive</button><button className="profile-switcher" onClick={onExit}><span className="identity-avatar">JR</span><span><strong>Judah Rumende</strong><small>Return to company site</small></span></button></aside>
    <main className={`app-main view-${view}`}><header className="app-topbar"><div className="mobile-brand"><button className="icon-button" aria-label="Open navigation" onClick={() => setMenu(true)}><Menu size={22} /></button><span className="brand-orb" /><strong>{view === 'overview' ? profiles.find(item => item.id === activeProfile)?.name || 'Profiles' : view === 'messages' ? roles.find(role => role.id === activeRole)?.name || 'Messages' : nav.find(n => n.id === view)?.label || 'Settings'}</strong></div><div className="breadcrumbs"><span>{view === 'global' || view === 'profiles' ? 'OrbityLabs' : profiles.find(item => item.id === activeProfile)?.name || 'No profile'}</span><ChevronRight size={12} /><strong>{view === 'settings' ? 'Settings' : nav.find(n => n.id === view)?.label}</strong></div><div className="topbar-actions"><button className="icon-button" aria-label="Search" onClick={() => setSearch(true)}><Search size={17} /></button><button className="icon-button" aria-label="Notifications" onClick={() => setNotes(v => !v)}><Bell size={17} /></button><button className="button button-quiet" onClick={() => setAgent(true)}><Sparkles size={15} /> Activity</button><button className="identity-avatar" aria-label="Return to landing page" onClick={onExit}>JR</button></div></header><div className="app-view">
      {view === 'overview' && <ConvoHome gateway={hermes.status} events={hermes.events} roles={roles} openThread={openThread} go={setView} newDirective={() => setDialog('directive')} />}
      {view === 'setup' && <SetupGuide gateway={hermes.status} completed={setupDone} setCompleted={setSetupDone} configure={() => setDialog('connection')} createJob={() => setDialog('job')} refresh={hermes.refresh} go={setView} />}
      {view === 'messages' && <Messages key={profileKey} profileId={profileKey} storageKey={scopedStorageKey('hermes.messages', profileKey)} gateway={hermes.status} events={hermes.events} roles={roles} activeRole={activeRole} setActiveRole={setActiveRole} closeThread={() => setView('overview')} run={hermes.run} settings={goSettings} addRole={() => setDialog('role')} addGroup={() => setDialog('group')} approvalMode={approvalMode} runtime={agentRuntimes[activeRole]} />}
      {view === 'profiles' && <ProfilesPage profiles={profiles} activeProfile={activeProfile} select={id => { setActiveProfile(id); setView('overview'); }} create={createProfile} />}
      {view === 'global' && <GlobalChat gateway={hermes.status} events={hermes.events} profiles={profiles} run={hermes.run} />}
      {view === 'work' && <Work tasks={tasks} toggleTask={toggleTask} deleteTask={deleteTask} add={() => setDialog('task')} />}
      {view === 'agents' && <AgentProviderManager roles={roles} gateway={hermes.status} runtimes={agentRuntimes} setRoute={setAgentRoute} add={() => setDialog('role')} />}
      {view === 'skills' && <SkillsPage profileId={profileKey} profileName={currentProfile?.name || 'this profile'} skills={skills} roles={roles} agentSkills={agentSkills} gateway={hermes.status} createSkill={createSkill} run={hermes.run} />}
      {view === 'knowledge' && <Knowledge sources={sources} add={() => setDialog('source')} />}
      {view === 'graphify' && <GraphifyPage profileId={profileKey} profileName={currentProfile?.name || 'this profile'} />}
      {view === 'connectors' && <ConnectorsPage />}
      {view === 'operations' && <OperationsMonitor profileId={activeProfile} profileName={currentProfile?.name || 'this profile'} />}
      {view === 'approvals' && <Approvals profileId={activeProfile} gateway={hermes.status} events={hermes.events} run={hermes.run} agentRuntimes={agentRuntimes} settings={goSettings} />}
      {view === 'timeline' && <RunTimeline profileId={activeProfile} roles={roles} />}
      {view === 'schedule' && <ScheduleView profileId={activeProfile} roles={roles} gateway={hermes.status} />}
      {view === 'pairing' && <PairingView />}
      {view === 'doctor' && <DoctorView profileId={activeProfile} />}
      {view === 'settings' && <><SettingsView gateway={hermes.status} refresh={hermes.refresh} configure={() => setDialog('connection')} job={() => setDialog('job')} /><AutonomyControl mode={approvalMode} setMode={setApprovalMode} /></>}
    </div></main>{!mobileCompanion && <nav className="mobile-app-nav" aria-label="Mobile command centre"><button className={view === 'overview' ? 'active' : ''} onClick={() => setView('overview')}><MessageSquare size={20} /><span>Convos</span></button><button className={view === 'setup' ? 'active' : ''} onClick={() => setView('setup')}><ListChecks size={20} /><span>Steps</span></button><button className="mobile-compose" onClick={() => setDialog('directive')} aria-label="New directive"><Pencil size={20} /></button><button className={view === 'work' ? 'active' : ''} onClick={() => setView('work')}><Inbox size={20} /><span>Work</span></button><button className={view === 'settings' ? 'active' : ''} onClick={goSettings}><Settings size={20} /><span>More</span></button></nav>}
    {menu && <button className="mobile-menu-scrim" aria-label="Close navigation" onClick={() => setMenu(false)} />}
    {profile && <ProfilePanel profileId={activeProfile} gateway={hermes.status} close={() => setProfile(false)} onExit={onExit} />}
    {agent && <AgentPanel profileId={profileKey} gateway={hermes.status} events={hermes.events} close={() => setAgent(false)} />}
    {notes && <Popover title="Notifications" close={() => setNotes(false)}>{hermes.events.length ? hermes.events.slice(0, 5).map((e, i) => <div className="popover-row" key={i}><strong>{e.type}</strong><small>{e.at ? time(e.at) : 'Now'}</small></div>) : <Empty title="No notifications" copy="Verified connection and run events will appear here." />}</Popover>}
    {search && <Palette profileId={profileKey} close={() => setSearch(false)} select={v => { setView(v); setSearch(false); }} />}
    {dialog && <Dialog kind={dialog} profileId={activeProfile} roles={roles} gateway={hermes.status} close={() => setDialog(null)} task={v => void createTask(v.title, v.area, v.state)} role={createRole} source={v => void createSource(v.title, v.detail)} configure={hermes.configure} run={hermes.run} job={hermes.job} />}
  </div>;
}

function WorkspaceMenu({ profiles, activeProfile, select, create }: { profiles: WorkspaceProfile[]; activeProfile: string; select: (id: string) => void; create: (name: string, kind: string, context: string, vaultPath: string) => void }) {
  const [open, setOpen] = useState(false), [name, setName] = useState(''), [kind, setKind] = useState(''), [context, setContext] = useState(''), [vaultPath, setVaultPath] = useState('');
  return <section className="workspace-menu" aria-label="Profile switcher">{profiles.map(item => <button key={item.id} className={item.id === activeProfile ? 'selected' : ''} onClick={() => select(item.id)}><span className="workspace-mark">{item.name.slice(0, 1).toUpperCase()}</span><span><strong>{item.name}</strong><small>{item.kind}</small></span>{item.id === activeProfile && <Check size={14} />}</button>)}{!profiles.length && <p>No profiles yet. Create one for a separate context.</p>}{open ? <form onSubmit={event => { event.preventDefault(); if (name.trim()) create(name, kind, context, vaultPath); }}><input autoFocus value={name} onChange={event => setName(event.target.value)} placeholder="Profile name" required /><input value={kind} onChange={event => setKind(event.target.value)} placeholder="Business or project" /><textarea value={context} onChange={event => setContext(event.target.value)} placeholder="What belongs in this profile?" rows={3} /><input value={vaultPath} onChange={event => setVaultPath(event.target.value)} placeholder="Obsidian vault path (optional)" /><button className="button button-primary" type="submit">Create profile</button></form> : <button className="workspace-new" onClick={() => setOpen(true)}><Plus size={15} /> New profile</button>}</section>;
}

function ProfilesPage({ profiles, activeProfile, select, create }: { profiles: WorkspaceProfile[]; activeProfile: string; select: (id: string) => void; create: (name: string, kind: string, context: string, vaultPath: string) => void }) {
  return <div className="page profiles-page"><Head title="Profiles" copy="Separate operating contexts for each business, project, and idea." /><div className="profiles-grid">{profiles.map(profile => <button className={`profile-card ${activeProfile === profile.id ? 'active' : ''}`} key={profile.id} onClick={() => select(profile.id)}><span className="profile-card-mark">{profile.name.slice(0, 1).toUpperCase()}</span><strong>{profile.name}</strong><small>{profile.kind}</small><p>{profile.context || 'No context added yet.'}</p>{profile.vault_path && <code>{profile.vault_path}</code>}<footer><span>Agents, work, and knowledge isolated</span>{activeProfile === profile.id && <span className="profile-active"><span className="status-dot live" /> Active</span>}</footer></button>)}{!profiles.length && <Empty title="Create your first profile" copy="Use the profile switcher in the sidebar to create a business, app, or experiment context." />}</div><div className="profile-global-note"><GlobeIcon /><div><strong>One assistant across everything</strong><p>All profiles is the global conversation. It can only use context that exists in your profiles and reports which profile it is referencing.</p></div></div></div>;
}

function GlobeIcon() { return <Network size={18} aria-hidden="true" />; }

function GlobalChat({ gateway, events, profiles, run }: { gateway: Gateway; events: Event[]; profiles: WorkspaceProfile[]; run: (input: string, session: string) => Promise<unknown> }) {
  const [draft, setDraft] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState(''), [pendingRun, setPendingRun] = useState('');
  const [messages, setMessages] = useStored<ChatMessage[]>('hermes.global.messages', []);
  const handled = useRef(new Set<string>());
  useEffect(() => { for (const item of events) { if (item.type !== 'run.event' || !item.data || !item.data.run_id) continue; const runId = String(item.data.run_id); const key = `${runId}:${JSON.stringify(item.data.data || {})}`; if (handled.current.has(key) || runId !== pendingRun) continue; handled.current.add(key); const text = extractResponseText(item.data.data); if (text && !/^(queued|accepted|started|completed)$/i.test(text)) { setMessages(current => [...current, { text, direction: 'incoming', status: 'sent' }]); setPendingRun(''); } } }, [events, pendingRun, setMessages]);
  const send = async () => { const text = draft.trim(); if (!text || busy) return; if (gateway.status !== 'online') return setError('Connect the runtime before asking across profiles.'); setBusy(true); setError(''); try { const globalContext = await fetchGlobalContext(); const context = globalContext.map(profile => `Profile: ${profile.name} (${profile.kind})\nContext: ${profile.context || 'No context supplied'}\nObsidian vault: ${profile.vault_path || 'Not configured'}\nAgents: ${profile.agents.map(a => `${a.name} — ${a.role}`).join('; ') || 'None configured'}\nKnowledge sources: ${profile.sources.join('; ') || 'None configured'}`).join('\n\n'); const result = await run(`You are the global OrbityLabs assistant. Answer across the following isolated profiles without mixing them. State which profile(s) you used. If context is missing, say so.\n\n${context}\n\nOperator question: ${text}`, 'jarvis-global'); setMessages(current => [...current, { text, direction: 'outgoing', status: 'sent' }]); const responseText = extractResponseText(result); const runId = result && typeof result === 'object' && ('run_id' in result || 'id' in result) ? String((result as { run_id?: unknown; id?: unknown }).run_id || (result as { id?: unknown }).id || '') : ''; if (responseText) setMessages(current => [...current, { text: responseText, direction: 'incoming', status: 'sent' }]); setPendingRun(runId); setDraft(''); } catch (e) { setError(e instanceof Error ? e.message : 'Global assistant could not accept the request.'); } finally { setBusy(false); } };
  return <div className="page global-chat-page"><Head title="All profiles" copy="Ask one question across your isolated workspaces." /><section className="global-chat"><header><div className="global-chat-mark"><Network size={20} /></div><div><h2>Global assistant</h2><p>{profiles.length ? `${profiles.length} profile${profiles.length === 1 ? '' : 's'} available as context` : 'Create profiles to give the assistant useful context'}</p></div></header><div className="global-scope">{profiles.map(profile => <span key={profile.id}><span className="status-dot live" />{profile.name}</span>)}</div><div className="global-stream">{messages.map((message, index) => <div className={`global-message ${message.direction}`} key={index}><span>{message.direction === 'incoming' ? 'OrbityLabs' : 'You'}</span><p>{message.text}</p></div>)}{!messages.length && <Empty title="No global questions yet" copy="Ask about a business, a project, or how your profiles connect." />}{error && <div className="form-error" role="alert">{error}</div>}</div><footer><textarea value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); send(); } }} placeholder="Ask across your profiles..." rows={2} /><button className="button button-primary" onClick={send} disabled={busy || !draft.trim()}>{busy ? 'Working...' : 'Ask assistant'} <ArrowRight size={14} /></button></footer></section></div>;
}

function Nav({ label, icon: Icon, active, onClick }: { id: View; label: string; icon: React.ElementType; active: boolean; onClick: () => void }) { return <button className={`app-nav-item ${active ? 'active' : ''}`} onClick={onClick}><Icon size={15} /><span>{label}</span></button>; }
type PairingInvite = { pairing_id: string; token: string; expires_at: number; lan_host?: string | null };

function PairingView() {
  const [invite, setInvite] = useState<PairingInvite | null>(null);
  const [status, setStatus] = useState('Create a laptop pairing code for your phone.');
  const create = async () => {
    setStatus('Creating secure pairing code...');
    try { const value = await fetch('/api/pairing/start', { method: 'POST' }).then(async r => { if (!r.ok) throw new Error('Could not create pairing code'); return r.json(); }); setInvite(value); setStatus(value.lan_host ? 'Open your phone camera and scan this code while both devices are on the same Wi-Fi.' : 'Pairing code created. Enter a laptop LAN address before scanning.'); } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not create pairing code.'); }
  };
  useEffect(() => { create(); }, []);
  const pairUrl = invite?.lan_host ? `${location.protocol}//${invite.lan_host}:${location.port}/?pair=${encodeURIComponent(invite.pairing_id)}&token=${encodeURIComponent(invite.token)}` : '';
  return <div className="page pairing-page"><Head title="Pair a phone" copy="Your phone connects to this laptop command centre. Hermes credentials remain on the laptop." /><section className="pairing-layout"><div className="pairing-copy"><span className="pairing-mark"><Laptop size={18} /></span><h2>Pair your phone to this laptop.</h2><p>{status}</p><ol><li>Keep this laptop and phone on the same Wi-Fi network.</li><li>Open the companion scanner on your phone.</li><li>Scan this single-use code. It expires after five minutes.</li></ol><button className="button button-primary" onClick={create}><RefreshCw size={14} /> New pairing code</button></div><div className="pairing-code" aria-live="polite">{pairUrl ? <><QRCodeSVG value={pairUrl} size={248} level="M" includeMargin /><small>Single-use · local network only</small></> : <div className="pairing-unavailable"><AlertCircle size={20} /><span>Could not determine this laptop's LAN address.</span></div>}</div></section></div>;
}

function MobilePairing() {
  const params = new URLSearchParams(location.search);
  const [message, setMessage] = useState(params.has('pair') ? 'Securing connection to your laptop...' : 'Scan the QR code shown in Pairing on your laptop.');
  const [manualUrl, setManualUrl] = useState('');
  const complete = async (pairingId: string, token: string) => {
    try { const response = await fetch(`/api/pairing/${encodeURIComponent(pairingId)}/complete`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token, device_name: 'Phone' }) }); const value = await response.json(); if (!response.ok) throw new Error(value.detail || 'Pairing could not be completed'); localStorage.setItem('hermes.mobile.pairing', JSON.stringify(value)); history.replaceState({}, '', location.pathname); setMessage('Paired. Opening messages...'); location.reload(); } catch (e) { setMessage(e instanceof Error ? e.message : 'Pairing could not be completed.'); }
  };
  useEffect(() => { const pairingId = params.get('pair'), token = params.get('token'); if (pairingId && token) void complete(pairingId, token); }, []);
  useEffect(() => { if (params.has('pair')) return; let scanner: Html5QrcodeScanner | null = null; try { scanner = new Html5QrcodeScanner('pairing-scanner', { fps: 10, qrbox: { width: 220, height: 220 } }, false); scanner.render(text => { try { const url = new URL(text); if (url.searchParams.has('pair') && url.searchParams.has('token')) location.assign(url.toString()); else setMessage('That QR code is not a laptop pairing code.'); } catch { setMessage('That QR code is not a valid pairing link.'); } }, () => undefined); } catch { setMessage('Camera scanner unavailable. Paste the pairing link from your laptop instead.'); } return () => { void scanner?.clear(); }; }, []);
  const openManual = () => { try { const url = new URL(manualUrl); location.assign(url.toString()); } catch { setMessage('Paste the full pairing link from your laptop.'); } };
  return <main className="mobile-pairing"><header><span className="brand-orb" /><strong>Hermes</strong></header><section><span className="pairing-mark"><Smartphone size={20} /></span><h1>Connect to your laptop</h1><p>{message}</p>{!params.has('pair') && <><div id="pairing-scanner" className="pairing-scanner" /><div className="pairing-divider"><span>or paste pairing link</span></div><div className="manual-pair"><input value={manualUrl} onChange={e => setManualUrl(e.target.value)} placeholder="http://192.168.../?pair=..." /><button onClick={openManual}>Connect</button></div></>}</section></main>;
}
function Head({ title, copy, children }: { title: string; copy: string; children?: React.ReactNode }) { return <header className="page-header"><div><h1>{title}</h1><p>{copy}</p></div>{children && <div className="page-actions">{children}</div>}</header>; }
function Panel({ title, subtitle }: { title: string; subtitle?: string }) { return <header className="panel-header"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div></header>; }
function statusText(g: Gateway) { return g.status === 'online' ? 'Verified online' : g.status === 'bridge_offline' ? 'Bridge unavailable' : g.status === 'offline' ? 'Hermes unreachable' : g.status === 'loading' ? 'Checking...' : 'Not configured'; }
function tone(g: Gateway): Status { return g.status === 'online' ? 'live' : g.status === 'offline' ? 'blocked' : 'idle'; }
function count(value: unknown, keys: string[]) { if (Array.isArray(value)) return value.length; if (value && typeof value === 'object') for (const key of keys) { const item = (value as Record<string, unknown>)[key]; if (Array.isArray(item)) return item.length; } return null; }
function time(value: string) { try { return new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(new Date(value)); } catch { return value; } }

type GuideStep = {
  id: string;
  title: string;
  summary: string;
  why: string;
  instructions: string[];
  command?: string;
  automatic?: 'bridge' | 'gateway' | 'profiles' | 'jobs';
  action?: 'configure' | 'refresh' | 'agents' | 'job' | 'settings';
};

const guideSteps: GuideStep[] = [
  {
    id: 'install-hermes',
    title: 'Install and start Hermes Agent',
    summary: 'Make sure the Hermes runtime is installed on the machine that will execute work.',
    why: 'Hermes is the runtime authority. Jarvis can direct and observe it, but cannot replace it.',
    instructions: ['Open Terminal on the Hermes host.', 'Install Hermes Agent using its official installation method.', 'Run the Hermes gateway and leave it running as a managed service for unattended work.', 'Confirm the gateway starts without an authentication or model-provider error.'],
    command: 'hermes gateway',
  },
  {
    id: 'enable-api',
    title: 'Enable the Hermes API server',
    summary: 'Expose the authenticated API used for health checks, runs, profiles, events, and jobs.',
    why: 'The command centre connects to Hermes through its supported server API rather than browser-side credentials or simulated agents.',
    instructions: ['Open the environment file for the Hermes profile you want Jarvis to control.', 'Set API_SERVER_ENABLED=true.', 'Choose an API_SERVER_PORT; the standard local example is 8642.', 'Set a strong API_SERVER_KEY, then restart the Hermes gateway.'],
    command: 'API_SERVER_ENABLED=true\nAPI_SERVER_PORT=8642',
  },
  {
    id: 'configure-bridge',
    title: 'Add Hermes credentials to Jarvis',
    summary: 'Keep the API key in the Jarvis server environment and enter only the gateway URL in the dashboard.',
    why: 'Server-side credentials prevent the Hermes key from appearing in the browser bundle or local storage.',
    instructions: ['Copy .env.example to .env in the Hermes Jarvis folder.', 'Set HERMES_API_KEY to the same API_SERVER_KEY configured in Hermes.', 'Optionally set HERMES_API_URL to the gateway URL.', 'Restart npm run server, then use Configure connection below.'],
    command: 'cp .env.example .env\n# Edit .env, then restart:\nnpm run server',
    automatic: 'bridge',
    action: 'configure',
  },
  {
    id: 'verify-gateway',
    title: 'Verify the live gateway connection',
    summary: 'Run a real readiness probe and confirm Jarvis reports Verified online.',
    why: 'A saved URL is not proof of a working connection. This step verifies authentication and upstream readiness.',
    instructions: ['Select Recheck connection.', 'If Hermes is unreachable, confirm its host, port, firewall, and gateway process.', 'If Hermes returns 401 or 403, check HERMES_API_KEY and restart Jarvis.', 'Continue only when the dashboard reports Verified online.'],
    automatic: 'gateway',
    action: 'refresh',
  },
  {
    id: 'review-profiles',
    title: 'Review discovered Hermes profiles',
    summary: 'Confirm the available profiles or model routes before assigning organisation roles.',
    why: 'Jarvis discovers profiles from Hermes but never invents role assignments.',
    instructions: ['Open the Agents page.', 'Review the profile count reported by Hermes model discovery.', 'Add planned organisation roles as needed.', 'Map profiles to roles only when the real profile metadata is available.'],
    automatic: 'profiles',
    action: 'agents',
  },
  {
    id: 'schedule-job',
    title: 'Create the first background job',
    summary: 'Schedule a bounded recurring directive through the Hermes Jobs API.',
    why: 'Hermes scheduled jobs continue independently of the browser; browser timers do not provide reliable 24/7 operation.',
    instructions: ['Choose a narrow, reversible first job.', 'Write a clear prompt with constraints and an expected output.', 'Choose a cron schedule and create the job.', 'Confirm the job appears in the verified job count before relying on it.'],
    automatic: 'jobs',
    action: 'job',
  },
  {
    id: 'production-controls',
    title: 'Complete production safeguards',
    summary: 'Protect the command centre before exposing it outside a trusted local network.',
    why: 'Hermes can use powerful tools. Internet-facing access needs explicit security and recovery controls.',
    instructions: ['Add command-centre authentication and least-privilege operator roles.', 'Terminate TLS at a trusted reverse proxy and restrict allowed origins.', 'Move secrets to a managed secret store and add mutation-route rate limits.', 'Configure a shared database, backups, monitoring, and alerting.', 'Test approval boundaries and recovery procedures before enabling consequential jobs.'],
  },
];

function SetupGuide({ gateway, completed, setCompleted, configure, createJob, refresh, go }: { gateway: Gateway; completed: string[]; setCompleted: React.Dispatch<React.SetStateAction<string[]>>; configure: () => void; createJob: () => void; refresh: () => void; go: (view: View) => void }) {
  const [selectedId, setSelectedId] = useState(guideSteps[0].id);
  const [copied, setCopied] = useState(false);
  const connectorCommand = 'npx --yes --package=github:judahrumende/HERMES-CONNECTOR orbitylabs-connect http://127.0.0.1:8642';
  const masterPrompt = `You are the Hermes setup operator for my Jarvis command centre. First inspect the current Hermes installation, gateway status, API configuration, available profiles, model routes, tools, and jobs. Do not invent values or claim success without verification. Then, in this order: (1) start or repair the Hermes gateway if it is installed; (2) enable its authenticated API server on port 8642 unless another configured port is required; (3) create or identify a strong API_SERVER_KEY without exposing it in chat; (4) verify /health/detailed and report the exact result; (5) inspect and summarize real profiles and model routes; (6) identify safe background jobs and propose bounded schedules; (7) explain any production safeguards still required. Ask for confirmation before destructive, external, financial, security-sensitive, or irreversible actions. At the end, give me only a concise checklist of completed, blocked, and awaiting-approval items, including the gateway URL I should connect to Jarvis. Never print API keys or fabricate agents, jobs, metrics, or completion.`;
  const selected = guideSteps.find(step => step.id === selectedId) || guideSteps[0];
  const observed = (step: GuideStep) => {
    if (step.automatic === 'bridge') return gateway.status !== 'bridge_offline' && gateway.status !== 'loading';
    if (step.automatic === 'gateway') return gateway.status === 'online';
    if (step.automatic === 'profiles') return count(gateway.models, ['data', 'models']) !== null;
    if (step.automatic === 'jobs') return (count(gateway.jobs, ['data', 'jobs']) || 0) > 0;
    return completed.includes(step.id);
  };
  const done = guideSteps.filter(observed).length;
  const toggle = (id: string) => setCompleted(current => current.includes(id) ? current.filter(item => item !== id) : [...current, id]);
  const runAction = () => {
    if (selected.action === 'configure') configure();
    else if (selected.action === 'refresh') refresh();
    else if (selected.action === 'agents') go('agents');
    else if (selected.action === 'job') createJob();
    else if (selected.action === 'settings') go('settings');
  };
  const [promptCopied, setPromptCopied] = useState(false);
  const copyCommand = async () => { try { await navigator.clipboard.writeText(connectorCommand); setCopied(true); window.setTimeout(() => setCopied(false), 1800); } catch { setCopied(false); } };
  const copyPrompt = async () => { try { await navigator.clipboard.writeText(masterPrompt); setPromptCopied(true); window.setTimeout(() => setPromptCopied(false), 1800); } catch { setPromptCopied(false); } };
  return <div className="page setup-page"><Head title="Steps to do" copy="Follow this checklist to move from a local dashboard to a verified Hermes operation."><span className="setup-progress-label"><strong>{done} of {guideSteps.length}</strong> complete</span></Head><section className="setup-connect-card"><div><span className="mono setup-eyebrow">START HERE</span><h2>Connect your Hermes gateway</h2><p>Run this from the Hermes Jarvis project folder. It verifies the gateway, then securely saves the connection.</p></div><div className="setup-command"><code>{connectorCommand}</code><button className="button button-primary" onClick={copyCommand}>{copied ? <Check size={14} /> : <CopyIcon />} {copied ? 'Copied' : 'Copy command'}</button></div><p className="setup-key-note"><strong>Where is the API key?</strong> Create or copy the <code>API_SERVER_KEY</code> configured on your Hermes host. Use that same value when the connector asks for the key; it is not generated by this dashboard and is never displayed in the browser.</p><div className="setup-prompt"><div><span className="mono setup-eyebrow">AUTOMATE SETUP IN HERMES</span><h3>Master setup prompt</h3><p>Copy this into Hermes. It will inspect the runtime, complete safe setup actions, and report anything needing your approval.</p></div><div className="setup-prompt-actions"><button className="button button-outline" onClick={copyPrompt}>{promptCopied ? <Check size={14} /> : <CopyIcon />} {promptCopied ? 'Copied' : 'Copy master prompt'}</button></div><pre><code>{masterPrompt}</code></pre></div></section><div className="guide-progress" aria-label={`${done} of ${guideSteps.length} setup steps complete`}><span style={{ width: `${done / guideSteps.length * 100}%` }} /></div><div className="guide-layout"><section className="guide-list" aria-label="Setup checklist"><Panel title="Setup checklist" subtitle="Select a step to see exact instructions" />{guideSteps.map((step, index) => { const isDone = observed(step); return <button key={step.id} className={`guide-step ${selected.id === step.id ? 'selected' : ''}`} onClick={() => setSelectedId(step.id)} aria-current={selected.id === step.id ? 'step' : undefined}><span className={`guide-check ${isDone ? 'complete' : ''}`}>{isDone ? <Check size={13} /> : index + 1}</span><span><strong>{step.title}</strong><small>{step.summary}</small></span><span className="guide-step-state">{step.automatic ? isDone ? 'Verified' : 'Waiting' : isDone ? 'Complete' : 'Manual'}</span><ChevronRight size={14} /></button>; })}</section><aside className="guide-detail"><header><span className={`guide-check ${observed(selected) ? 'complete' : ''}`}>{observed(selected) ? <Check size={15} /> : guideSteps.indexOf(selected) + 1}</span><div><h2>{selected.title}</h2><p>{selected.summary}</p></div></header><div className="guide-why"><strong>Why this matters</strong><p>{selected.why}</p></div><ol>{selected.instructions.map((instruction, index) => <li key={index}><span>{index + 1}</span><p>{instruction}</p></li>)}</ol>{selected.command && <pre><code>{selected.command}</code></pre>}<footer>{selected.automatic ? <><span className={`verification-state ${observed(selected) ? 'verified' : ''}`}><span className={`status-dot ${observed(selected) ? 'live' : 'idle'}`} /> {observed(selected) ? 'Verified from current app state' : 'Not verified yet'}</span>{selected.action && <button className="button button-secondary" onClick={runAction}>{selected.action === 'configure' ? 'Configure connection' : selected.action === 'refresh' ? 'Recheck connection' : selected.action === 'agents' ? 'Open Agents' : 'Create background job'}</button>}</> : <button className="button button-outline" onClick={() => toggle(selected.id)}>{observed(selected) ? 'Mark as incomplete' : 'Mark step complete'}</button>}</footer></aside></div></div>;
}

function ConvoHome({ gateway, events, roles, openThread, go, newDirective }: { gateway: Gateway; events: Event[]; roles: Role[]; openThread: (id: string) => void; go: (view: View) => void; newDirective: () => void }) {
  const recentRoles = roles.slice(0, 5);
  const observedEvents = events.slice(0, 5);
  const ceo = roles.find(role => /ceo/i.test(`${role.name} ${role.role}`)) || roles[0];
  const gatewayOnline = gateway.status === 'online';
  return <div className="dashboard-home">
    <header className="dashboard-home-header">
      <div><h1>Command centre</h1><p>A focused operating view for your laptop workspace.</p></div>
      <div className="dashboard-home-actions"><button className="button button-quiet" onClick={() => go('operations')}><Monitor size={15} /> Operations</button><button className="button button-primary" onClick={newDirective}><Pencil size={15} /> New directive</button></div>
    </header>
    <div className="dashboard-home-grid">
      <section className="dashboard-home-panel dashboard-brief" aria-labelledby="ceo-brief-title">
        <div className="dashboard-panel-topline"><span className={`status-dot ${tone(gateway)}`} /><span>{gatewayOnline ? 'Verified runtime' : 'Runtime not verified'}</span></div>
        <div className="dashboard-ceo"><AgentAvatar role={ceo} featured size="hero" /><div><h2 id="ceo-brief-title">{ceo ? ceo.name : 'Create a CEO agent'}</h2><p>{ceo ? ceo.role : 'A CEO coordinates this profile once you add one.'}</p></div></div>
        <p className="dashboard-brief-copy">{gatewayOnline ? 'Give the CEO an outcome and constraints. Its work begins through the verified laptop runtime.' : 'Connect the runtime before directing work that should leave this command centre.'}</p>
        <div className="dashboard-brief-footer"><button className="dashboard-inline-action" onClick={() => ceo ? openThread(ceo.id) : go('agents')}>{ceo ? 'Open CEO conversation' : 'Create an agent'} <ArrowRight size={14} /></button><span>{gateway.base_url || 'Local workspace'}</span></div>
      </section>
      <section className="dashboard-home-panel dashboard-attention" aria-labelledby="attention-title">
        <header><div><h2 id="attention-title">Needs your attention</h2><p>Only current, observed state is shown here.</p></div><button className="icon-button" onClick={() => go('setup')} aria-label="Open setup"><ChevronRight size={17} /></button></header>
        <div className="dashboard-state-row"><span className={`dashboard-state-icon ${tone(gateway)}`}>{gatewayOnline ? <Check size={14} /> : <AlertCircle size={14} />}</span><div><strong>Runtime connection</strong><small>{gateway.error || statusText(gateway)}</small></div><button onClick={() => go(gatewayOnline ? 'operations' : 'setup')}>{gatewayOnline ? 'Inspect' : 'Set up'}</button></div>
        <div className="dashboard-state-row"><span className="dashboard-state-icon idle"><Activity size={14} /></span><div><strong>Recorded events</strong><small>{observedEvents.length ? `${observedEvents.length} recent event${observedEvents.length === 1 ? '' : 's'} available` : 'No runtime events observed yet'}</small></div><button onClick={() => go('timeline')}>View</button></div>
      </section>
      <section className="dashboard-home-panel dashboard-agent-list" aria-labelledby="agent-list-title">
        <header><div><h2 id="agent-list-title">Agents</h2><p>Configured in this profile</p></div><button className="dashboard-text-action" onClick={() => go('agents')}>Manage <ArrowRight size={13} /></button></header>
        {recentRoles.length ? <div>{recentRoles.map((role, index) => <button className="dashboard-agent-row" key={role.id} onClick={() => openThread(role.id)}><AgentAvatar role={role} featured={role.id === ceo?.id || index === 0} /><span><strong>{role.name}</strong><small>{role.role}</small></span><span className="dashboard-row-state">{role.id === ceo?.id ? 'CEO' : 'Profile agent'}</span><ChevronRight size={15} /></button>)}</div> : <div className="dashboard-empty"><Bot size={18} /><p>No agents exist in this profile yet.</p><button onClick={() => go('agents')}>Add an agent</button></div>}
      </section>
      <section className="dashboard-home-panel dashboard-observations" aria-labelledby="observations-title">
        <header><div><h2 id="observations-title">Recent observations</h2><p>Bridge and runtime events</p></div><button className="dashboard-text-action" onClick={() => go('operations')}>Open monitor <ArrowRight size={13} /></button></header>
        {observedEvents.length ? <div>{observedEvents.map((event, index) => <div className="dashboard-event-row" key={`${event.type}-${event.at || index}`}><span className="status-dot live" /><strong>{event.type}</strong><time>{event.at ? time(event.at) : 'Just observed'}</time></div>)}</div> : <div className="dashboard-empty"><Activity size={18} /><p>Events appear here only after the local bridge observes them.</p></div>}
      </section>
    </div>
  </div>;
}

function AgentAvatar({ role, featured = false, size = 'normal' }: { role?: Role; featured?: boolean; size?: 'normal' | 'large' | 'hero' }) { return <span className={`agent-avatar ${featured ? 'featured' : ''} ${size}`} aria-hidden="true">{role?.initials || ''}<span className={`presence ${featured ? 'orange' : ''}`} /></span>; }

function Overview({ gateway, events, refresh, message, configure }: { gateway: Gateway; events: Event[]; refresh: () => void; message: () => void; configure: () => void }) { const profiles = count(gateway.models, ['data','models']), jobs = count(gateway.jobs, ['data','jobs']); return <div className="page overview-page"><Head title="Organisation overview" copy="A verified operating picture of the command centre and connected runtime."><button className="button button-outline" onClick={refresh}><RefreshCw size={14} /> Refresh</button><button className="button button-secondary" onClick={message}>Message CEO <ArrowRight size={14} /></button></Head><div className="system-strip"><Strip icon={Network} label="Gateway" value={statusText(gateway)} state={tone(gateway)} /><Strip icon={Users} label="Profiles" value={profiles === null ? 'Not observed' : `${profiles} discovered`} state={profiles === null ? 'idle' : 'live'} /><Strip icon={Zap} label="Jobs" value={jobs === null ? 'Not observed' : `${jobs} configured`} state={jobs === null ? 'idle' : 'live'} /><Strip icon={Database} label="Events" value={events.length ? `${events.length} received` : 'None received'} state={events.length ? 'live' : 'idle'} /></div><div className="dashboard-grid"><section className="dashboard-panel work-queue-panel"><Panel title="Setup queue" subtitle="Infrastructure required for real operation" /><div className="queue-columns"><Queue title="Required" state="blocked"><Card title="Connect Hermes Gateway" area="Infrastructure" state={tone(gateway)} /><Card title="Choose persistent storage" area="Architecture" state="draft" /></Queue><Queue title="Review" state="draft"><Card title="Define approval boundaries" area="Governance" state="draft" /></Queue><Queue title="Complete" state="idle"><div className="empty-queue"><Check size={14} /><span>{gateway.status === 'online' ? 'Gateway verified' : 'No completed setup'}</span></div></Queue></div></section><section className="dashboard-panel attention-panel"><Panel title="Attention" subtitle="What needs an operator" /><div className="attention-row"><span className={`attention-icon ${tone(gateway)}`}>{gateway.status === 'online' ? <Check size={14} /> : <AlertCircle size={14} />}</span><div><strong>Hermes Gateway</strong><small>{gateway.error || statusText(gateway)}</small></div></div><button className="panel-link" onClick={configure}>Open connection settings <ArrowRight size={13} /></button></section><section className="dashboard-panel activity-feed-panel"><Panel title="Organisation activity" subtitle="Verified bridge and Hermes events" />{events.length ? <div className="event-list">{events.slice(0, 8).map((e, i) => <div className="event-row" key={i}><span className="status-dot live" /><strong>{e.type}</strong><span>{e.at ? time(e.at) : 'Now'}</span></div>)}</div> : <Empty title="No live events yet" copy="Connection, run, tool, and job events appear only when observed." />}</section></div></div>; }
function Strip({ icon: Icon, label, value, state }: { icon: React.ElementType; label: string; value: string; state: Status }) { return <div className="system-strip-item"><span className="strip-icon"><Icon size={14} /></span><div><span>{label}</span><strong>{value}</strong></div><span className={`status-dot ${state}`} /></div>; }
function Queue({ title, state, children }: { title: string; state: Status; children: React.ReactNode }) { return <div className="queue-column"><header><span><span className={`status-ring ${state}`} />{title}</span></header>{children}</div>; }
function Card({ title, area, state }: { title: string; area: string; state: Status }) { return <article className="work-card"><div><span className={`task-state ${state}`} /><strong>{title}</strong></div><footer><span className="quiet-badge">{area}</span></footer></article>; }

function Messages({ profileId, storageKey, gateway, events, roles, activeRole, setActiveRole, closeThread, run, settings, addRole, addGroup, approvalMode, runtime }: { profileId: string; storageKey: string; gateway: Gateway; events: Event[]; roles: Role[]; activeRole: string; setActiveRole: (id: string) => void; closeThread: () => void; run: (input: string, session: string, runtime?: AgentRuntime) => Promise<unknown>; settings: () => void; addRole: () => void; addGroup: () => void; approvalMode: ApprovalMode; runtime?: AgentRuntime }) {
  const realProfileId = profileId === 'unassigned' ? '' : profileId;
  const [draft, setDraft] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState(''), [skills, setSkills] = useState(false), [pendingRun, setPendingRun] = useState('');
  const [inspectRunId, setInspectRunId] = useState<string | null>(null);
  const { messages: sqlMessages, saveMessage } = useProfileMessages(realProfileId, activeRole);
  const previews = useMessagePreviews(realProfileId);
  const { notes: agentNotes, setNotes: setAgentNotes, save: saveAgentNotes } = useAgentNotes(realProfileId, activeRole);
  const [localMessages, setLocalMessages] = useStored<Record<string, ChatMessage[]>>(storageKey, {});
  const handledEvents = useRef(new Set<string>());
  const role = roles.find(r => r.id === activeRole) || roles[0];
  const thread: ChatMessage[] = sqlMessages.length > 0
    ? sqlMessages.map(m => ({ text: m.text, direction: m.direction as 'outgoing' | 'incoming', status: 'sent' as const }))
    : (localMessages[activeRole] || []).map(normalizeChatMessage).filter(Boolean) as ChatMessage[];

  useEffect(() => {
    for (const item of events) {
      if (item.type !== 'run.event' || !item.data) continue;
      const runId = typeof item.data.run_id === 'string' ? item.data.run_id : '';
      const event = typeof item.data.event === 'string' ? item.data.event : '';
      const key = `${runId}:${event}:${JSON.stringify(item.data.data || {})}`;
      if (!runId || handledEvents.current.has(key)) continue;
      handledEvents.current.add(key);
      if (runId !== pendingRun || /tool|thinking|started/i.test(event)) continue;
      const responseText = extractResponseText(item.data.data);
      if (responseText && !/^(queued|accepted|started|completed)$/i.test(responseText)) {
        void saveMessage('incoming', responseText, runId);
        if (!realProfileId) setLocalMessages(m => ({ ...m, [activeRole]: [...(m[activeRole] || []).map(normalizeChatMessage).filter(Boolean) as ChatMessage[], { text: responseText, direction: 'incoming', status: 'sent' }] }));
        setPendingRun('');
      }
      if (/completed|failed|error|cancelled/i.test(event)) setPendingRun('');
    }
  }, [events, pendingRun, activeRole, saveMessage, realProfileId, setLocalMessages]);

  if (!role) return <div className="messages-layout imessage-layout"><section className="thread-pane"><div className="compact-empty"><strong>No conversations yet</strong><p>Create or discover a real agent profile before sending a message.</p><button className="button button-outline" onClick={addRole}>Create an agent</button></div></section></div>;

  const send = async () => {
    const text = draft.trim(); if (!text || busy) return;
    if (gateway.status !== 'online') { setError('Not sent. The runtime is not available.'); return; }
    setBusy(true); setError('');
    try {
      const policy = approvalMode === 'auto_safe'
        ? 'Routine, reversible actions are pre-approved by the operator. Pause for confirmation before irreversible, external, paid, destructive, credential, account-creation, or security-sensitive actions.'
        : 'Ask for operator approval before consequential actions.';
      const result = await run(`${policy}\n\nDirective: ${text}`, `profile-${profileId}-agent-${activeRole}`, runtime);
      const runId = result && typeof result === 'object' && ('run_id' in result || 'id' in result) ? String((result as { run_id?: unknown; id?: unknown }).run_id || (result as { id?: unknown }).id || '') : '';
      const responseText = extractResponseText(result);
      await saveMessage('outgoing', text, runId);
      if (!realProfileId) setLocalMessages(m => ({ ...m, [activeRole]: [...(m[activeRole] || []).map(normalizeChatMessage).filter(Boolean) as ChatMessage[], { text, direction: 'outgoing', status: 'sent' }] }));
      if (responseText && !runId) {
        await saveMessage('incoming', responseText, '');
        if (!realProfileId) setLocalMessages(m => ({ ...m, [activeRole]: [...(m[activeRole] || []).map(normalizeChatMessage).filter(Boolean) as ChatMessage[], { text: responseText, direction: 'incoming', status: 'sent' }] }));
      }
      setPendingRun(runId); setDraft('');
    } catch (e) { setError(e instanceof Error ? e.message : 'The runtime did not accept the directive. It was not sent.'); }
    finally { setBusy(false); }
  };

  const stopPending = async () => {
    if (!pendingRun) return;
    try { await stopRun(pendingRun); setPendingRun(''); } catch { /* let the run finish */ }
  };

  const getPreview = (agentId: string) => previews.find(p => p.agent_id === agentId)?.text || (localMessages[agentId] || []).map(normalizeChatMessage).filter(Boolean).at(-1)?.text;

  return <div className="messages-layout imessage-layout">
    <aside className="conversation-pane"><header><div><h1>Messages</h1><p>{gateway.status === 'online' ? 'Hermes transport available' : 'Local-only conversations'}</p></div><button className="icon-button" onClick={addRole} aria-label="Add planned agent"><Pencil size={19} /></button></header><label className="message-search"><Search size={16} /><input placeholder="Search" onChange={() => undefined} /></label><div className="conversation-list">{roles.map((r, index) => { const preview = getPreview(r.id); return <button key={r.id} className={`conversation-row ${activeRole === r.id ? 'selected' : ''}`} onClick={() => setActiveRole(r.id)}><AgentAvatar role={r} featured={index === 0} /><span><strong>{r.name}</strong><small>{r.role}</small><em>{preview || (gateway.status === 'online' ? 'Ready for a directive' : 'Saved locally')}</em></span><time>{activeRole === r.id ? 'Now' : ''}</time></button>; })}</div></aside>
    <section className="thread-pane"><header className="thread-header"><div><button className="icon-button mobile-back" onClick={closeThread} aria-label="Back"><ChevronLeft size={23} /></button><AgentAvatar role={role} featured={role?.id === 'ceo'} /><span><strong>{role?.name}</strong><small>{gateway.status === 'online' ? 'Hermes available' : 'Local only'}</small></span></div><button className="thread-add" onClick={addGroup} aria-label="Create group chat" title="Create group chat"><Plus size={22} /></button></header>
      <div className="thread-stream"><div className="thread-intro"><AgentAvatar role={role} featured={role?.id === 'ceo'} size="large" /><h2>{role?.name}</h2><p>{role?.role}</p><button onClick={() => setSkills(true)}>See its controls</button></div><div className="system-message"><span className="mini-avatar">JR</span> You direct this agent · Authority stays with you</div>{thread.map((message, index) => { const msgRunId = sqlMessages[index]?.run_id || ''; return <div className={`imessage-row ${message.direction}`} key={`${message.direction}-${index}`}><div className="imessage-bubble" onClick={() => msgRunId ? setInspectRunId(msgRunId === inspectRunId ? null : msgRunId) : undefined} style={msgRunId ? { cursor: 'pointer' } : undefined}>{message.text}</div><small>{message.direction === 'incoming' ? 'Received from Hermes' : 'Sent to Hermes'}{msgRunId && <span className="run-id-chip mono" style={{ marginLeft: 6 }}>{msgRunId.slice(0, 8)}</span>}</small>{inspectRunId === msgRunId && msgRunId && <RunInspector profileId={realProfileId} runId={msgRunId} close={() => setInspectRunId(null)} />}</div>; })}{pendingRun && <div className="agent-message agent-working" role="status"><AgentAvatar role={role} featured={role?.id === 'ceo'} /><div><strong>{role?.name}</strong><p>Working on your directive...</p></div><button className="icon-button stop-run-btn" onClick={stopPending} title="Stop this run" aria-label="Stop run"><Square size={14} /></button></div>}{!thread.length && !pendingRun && <div className="agent-message"><AgentAvatar role={role} featured={role?.id === 'ceo'} /><div><strong>{role?.name}</strong><p>{gateway.status === 'online' ? 'What outcome should I coordinate for you?' : 'Connect Hermes to send verified directives. I will not simulate a reply while the runtime is offline.'}</p></div></div>}{error && <div className="form-error" role="alert">{error}</div>}</div>
      <div className="composer-wrap"><div className="identity-selector"><span className="mini-avatar">JR</span><span>Chat as Judah</span></div><div className="composer"><button className="composer-tool" disabled title="Storage provider required" aria-label="Photo library"><ImageIcon size={20} /></button><button className="composer-tool" disabled title="Camera access is not configured" aria-label="Camera"><Camera size={20} /></button><button className="composer-tool" disabled title="Voice input is not configured" aria-label="Voice message"><Mic size={20} /></button><textarea value={draft} onChange={e => setDraft(e.target.value)} maxLength={12000} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }} placeholder={`Message ${role?.name || 'Hermes'}`} rows={1} /><button className="send-button" onClick={send} disabled={!draft.trim() || busy} aria-label="Send">{busy ? <RefreshCw className="spin" size={16} /> : <Send size={17} />}</button></div><p>{realProfileId ? 'Messages saved to profile database' : gateway.status === 'online' ? 'Creates a verified Hermes run' : 'Saved locally until Hermes is connected'}</p></div>
    </section>
    <aside className="thread-inspector"><header><h2>Agent controls</h2><button className="icon-button" onClick={settings} aria-label="Settings"><Settings size={18} /></button></header><AgentAvatar role={role} featured={role?.id === 'ceo'} size="large" /><h3>{role?.name}</h3><p>{role?.role}</p><dl><div><dt>Session</dt><dd className="mono">profile-{profileId.slice(0, 8)}...</dd></div><div><dt>Provider</dt><dd>{runtime?.provider || 'Gateway default'}</dd></div><div><dt>Model</dt><dd className="mono">{runtime?.model || 'Gateway default'}</dd></div><div><dt>Authority</dt><dd>{approvalMode === 'auto_safe' ? 'Auto-approved routine work' : 'Operator approval required'}</dd></div><div><dt>Status</dt><dd>{statusText(gateway)}</dd></div><div><dt>History</dt><dd>{sqlMessages.length > 0 ? `${sqlMessages.length} messages in database` : 'Local only'}</dd></div></dl><button className="inspector-skills" onClick={() => setSkills(true)}>View controls and skills</button><div className={`policy-badge ${approvalMode === 'auto_safe' ? 'enabled' : ''}`}><span className="status-dot" /><span>{approvalMode === 'auto_safe' ? 'Approve for me is on' : 'Approval gates are on'}</span></div>{realProfileId && <div className="agent-notes-section"><label htmlFor="agent-notes-input"><strong>Context notes</strong><span>Prepended to every loop and directive run</span></label><textarea id="agent-notes-input" className="agent-notes-input" value={agentNotes} onChange={e => setAgentNotes(e.target.value)} onBlur={e => { void saveAgentNotes(e.target.value); }} placeholder="Persistent context for this agent — goals, constraints, current focus..." rows={5} maxLength={10000} /></div>}<div className="context-note"><ShieldCheck size={17} /><p>The selected model is sent only with this agent's run. It does not alter other agents or the gateway default.</p></div></aside>
    {skills && <div className="skills-sheet" onClick={() => setSkills(false)}><section onClick={event => event.stopPropagation()}><header><div><AgentAvatar role={role} featured={role?.id === 'ceo'} /><span><strong>{role?.name}</strong><small>Controls and capabilities</small></span></div><button className="icon-button" onClick={() => setSkills(false)}><X size={20} /></button></header><div><h2>What this agent can do</h2><p>{gateway.status === 'online' ? 'Capabilities come from the connected Hermes profile. Open Agents to inspect discovered profile data.' : 'No live skills are available because Hermes is not connected.'}</p><button className="button button-outline" onClick={() => { setSkills(false); settings(); }}>Open connection settings</button></div></section></div>}
  </div>;
}

function Work({ tasks, toggleTask, deleteTask, add }: { tasks: Task[]; toggleTask: (id: string) => void; deleteTask: (id: string) => void; add: () => void }) { const [filter, setFilter] = useState('all'); const visible = filter === 'all' ? tasks : tasks.filter(t => t.state === filter); return <div className="page"><Head title="Work" copy="Local setup tasks and verified Hermes work in one queue."><button className="button button-secondary" onClick={add}><Plus size={14} /> Add local task</button></Head><div className="table-panel"><div className="table-toolbar"><div className="segmented">{[['all','All work'],['blocked','Required'],['draft','Review'],['live','Complete']].map(([id,label]) => <button key={id} className={filter === id ? 'active' : ''} onClick={() => setFilter(id)}>{label}</button>)}</div></div><div className="data-table work-table"><div className="table-head"><span>Status</span><span>Task</span><span>Area</span><span>Owner</span><span>Runtime</span><span /></div>{visible.map(t => <div className="table-row" key={t.id}><button className="state-button" onClick={() => toggleTask(t.id)}><span className={`status-ring ${t.state}`} /> {t.state === 'blocked' ? 'Required' : t.state === 'live' ? 'Complete' : 'Draft'}</button><strong>{t.title}</strong><span className="quiet-badge">{t.area}</span><span>Unassigned</span><span className="mono">Local</span><button className="icon-button" aria-label={`Delete ${t.title}`} onClick={() => deleteTask(t.id)}><X size={14} /></button></div>)}{!visible.length && <Empty title="No work in this view" copy="Choose another filter or add a local task." />}</div></div></div>; }
function Agents({ roles, gateway, add }: { roles: Role[]; gateway: Gateway; add: () => void }) { const profiles = count(gateway.models, ['data','models']); return <div className="page"><Head title="Agents" copy="Planned roles plus profiles discovered from Hermes."><button className="button button-secondary" onClick={add}><Plus size={14} /> Add planned role</button></Head><div className="agents-layout"><section className="table-panel"><Panel title="Organisation roster" subtitle={profiles === null ? 'No profiles observed' : `${profiles} profiles discovered`} /><div className="data-table agent-table"><div className="table-head"><span>Agent</span><span>Role</span><span>Status</span><span>Model</span><span>Workspace</span><span /></div>{roles.map(r => <div className="table-row" key={r.id}><span className="agent-cell"><span className="avatar">{r.initials}</span><strong>{r.name}</strong></span><span>{r.role}</span><span><span className={`status-dot ${tone(gateway)}`} /> {gateway.status === 'online' ? 'Gateway available' : 'Offline'}</span><span className="mono">Not assigned</span><span>Local plan</span><span /></div>)}</div></section><aside className="detail-panel"><Panel title="Profile sync" subtitle="Automatic model discovery" /><div className="setup-sequence"><Step title="Connect Gateway" detail={statusText(gateway)} /><Step title="Discover profiles" detail="Every successful probe refreshes /v1/models." /><Step title="Map organisation" detail="Assignments remain explicit, never inferred." /></div></aside></div></div>; }
function Step({ title, detail }: { title: string; detail: string }) { return <div className="setup-step"><span className="setup-index"><Circle size={10} /></span><div><strong>{title}</strong><p>{detail}</p></div></div>; }
function Knowledge({ sources, add }: { sources: Source[]; add: () => void }) { const [query, setQuery] = useState(''); const visible = useMemo(() => sources.filter(s => `${s.title} ${s.detail}`.toLowerCase().includes(query.toLowerCase())), [sources, query]); return <div className="page"><Head title="Knowledge" copy="Source plans remain truthful until a connector is configured."><label className="search-field page-search"><Search size={14} /><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search sources" /></label><button className="button button-secondary" onClick={add}><Plus size={14} /> Add source</button></Head><div className="knowledge-layout"><section className="table-panel"><Panel title="Sources" subtitle={`${sources.length} local source plans`} />{visible.map(s => <div className="knowledge-row" key={s.id}><span className="source-icon"><Database size={16} /></span><div><strong>{s.title}</strong><small>{s.detail}</small></div><span className="quiet-badge">Local plan</span></div>)}{!visible.length && <Empty title="No matching sources" copy="Try another search." />}</section><aside className="detail-panel"><Panel title="Retrieval policy" subtitle="Unavailable until a provider is connected" /><dl className="stacked-metadata"><div><dt>Index</dt><dd>Not available</dd></div><div><dt>Embeddings</dt><dd>Not selected</dd></div><div><dt>Access policy</dt><dd>Not defined</dd></div></dl></aside></div></div>; }
function RunInspector({ profileId, runId, close }: { profileId: string; runId: string; close: () => void }) {
  const { toolEvents } = useProfileToolEvents(profileId, runId);
  return <div className="run-inspector" onClick={e => e.stopPropagation()}>
    <header><strong>Run <span className="mono">{runId.slice(0, 8)}</span></strong><button className="icon-button" onClick={close}><X size={13} /></button></header>
    {toolEvents.length === 0
      ? <p className="quiet-text">No tool events recorded for this run.</p>
      : toolEvents.map(te => <div key={te.id} className={`inspector-tool-row ${te.status}`}>
          <code className="tool-name">{te.tool_name}</code>
          <span className={`tool-status-badge ${te.status}`}>{te.status}</span>
          <span className="tool-duration mono">{te.duration_ms}ms</span>
          <details><summary>Evidence</summary><pre className="mono inspector-payload">{JSON.stringify({ input: te.input, output: te.output }, null, 2)}</pre></details>
        </div>)}
  </div>;
}

function Approvals({ profileId, gateway, events, run, agentRuntimes, settings }: { profileId: string; gateway: Gateway; events: Event[]; run: (input: string, session: string, runtime?: AgentRuntime) => Promise<unknown>; agentRuntimes: Record<string, AgentRuntime>; settings: () => void }) {
  const [tab, setTab] = useState<'Pending' | 'Resolved'>('Pending');
  const { approvals, load, decideApproval } = useProfileApprovals(profileId);
  const [deciding, setDeciding] = useState('');
  const pending = approvals.filter(a => a.state === 'pending');
  const resolved = approvals.filter(a => a.state !== 'pending');
  const visible = tab === 'Pending' ? pending : resolved;

  const decide = async (id: string, state: 'approved' | 'denied') => {
    setDeciding(id);
    try {
      const updated = await decideApproval(id, state);
      if (state === 'approved' && updated.run_id) {
        const approval = approvals.find(a => a.id === id);
        if (approval) {
          const rt = agentRuntimes[approval.agent_id];
          await run(JSON.stringify(approval.payload), approval.session_id || `profile-${profileId}-approval-${id}`, rt);
        }
      }
    } catch { /* reflect error in list refresh */ load(); }
    finally { setDeciding(''); }
  };

  return <div className="page">
    <Head title="Approvals" copy="High-impact decisions wait for explicit human authority.">
      <button className="button button-outline" onClick={() => exportApprovals(profileId, 'json')} title="Export as JSON"><Download size={14} /> JSON</button>
      <button className="button button-outline" onClick={() => exportApprovals(profileId, 'csv')} title="Export as CSV"><FileJson size={14} /> CSV</button>
    </Head>
    <div className="approvals-shell">
      <div className="approval-tabs">
        {(['Pending', 'Resolved'] as const).map(v => <button key={v} className={tab === v ? 'active' : ''} onClick={() => setTab(v)}>{v} {v === 'Pending' && pending.length > 0 ? <span className="badge">{pending.length}</span> : null}</button>)}
      </div>
      {visible.length === 0
        ? <div className="approval-empty"><span className="empty-symbol"><ShieldCheck size={20} /></span><h2>No {tab.toLowerCase()}</h2><p>{tab === 'Pending' ? 'Requests appear when Hermes pauses for your authority. Nothing is waiting right now.' : 'No resolved approvals yet.'}</p>{gateway.status !== 'online' && <button className="button button-outline" onClick={settings}>Review connection requirements</button>}</div>
        : <div className="approval-list">{visible.map(a => {
            const isBusy = deciding === a.id;
            const payloadKeys = Object.keys(a.payload || {});
            return <div key={a.id} className={`approval-card ${a.state}`}>
              <div className="approval-card-head">
                <span className={`approval-kind-badge ${a.kind}`}>{a.kind}</span>
                <time className="mono">{a.created_at.slice(0, 19).replace('T', ' ')}</time>
              </div>
              <p className="approval-summary">{a.summary}</p>
              {payloadKeys.length > 0 && <details className="approval-payload"><summary>Payload ({payloadKeys.length} keys)</summary><pre className="mono">{JSON.stringify(a.payload, null, 2)}</pre></details>}
              {a.run_id && <div className="approval-run-id mono">run: {a.run_id}</div>}
              {a.state === 'pending'
                ? <div className="approval-actions">
                    <button className="button button-primary" onClick={() => decide(a.id, 'approved')} disabled={isBusy}>{isBusy ? 'Working...' : 'Approve'}</button>
                    <button className="button button-danger" onClick={() => decide(a.id, 'denied')} disabled={isBusy}>Deny</button>
                  </div>
                : <div className="approval-resolved-state"><span className={`status-dot ${a.state === 'approved' ? 'green' : 'red'}`} />{a.state} {a.decided_at ? `· ${a.decided_at.slice(0, 19).replace('T', ' ')}` : ''}</div>}
            </div>;
          })}</div>
      }
    </div>
  </div>;
}

function DoctorView({ profileId }: { profileId: string }) {
  const { report, loading, error, load } = useDoctorReport();
  const statusColor = (s: string) => s === 'ok' ? 'green' : s === 'warning' ? 'yellow' : 'red';
  return <div className="page">
    <Head title="Doctor" copy="Live health check for the local OrbityLabs bridge and runtime.">
      <button className="button button-outline" onClick={load} disabled={loading}><RefreshCw size={14} className={loading ? 'spin' : ''} /> {loading ? 'Checking...' : 'Recheck'}</button>
    </Head>
    {error && <div className="form-error" role="alert">{error}</div>}
    {report && <>
      <section className="doctor-checks">
        {report.checks.map((c, i) => <div key={i} className={`doctor-check ${c.status}`}>
          <span className={`status-dot ${statusColor(c.status)}`} />
          <div><strong>{c.name}</strong><p>{c.detail}</p></div>
          <span className={`doctor-badge ${c.status}`}>{c.status}</span>
        </div>)}
      </section>
      <div className="doctor-meta">
        <section className="doctor-card">
          <h3>Database</h3>
          <dl className="stacked-metadata">{Object.entries(report.db_stats).map(([k, v]) => <div key={k}><dt className="mono">{k}</dt><dd>{v}</dd></div>)}</dl>
        </section>
        <section className="doctor-card">
          <h3>Gateway</h3>
          <dl className="stacked-metadata">{Object.entries(report.gateway).filter(([, v]) => v !== null && v !== undefined).slice(0, 6).map(([k, v]) => <div key={k}><dt className="mono">{k}</dt><dd className="mono">{String(v)}</dd></div>)}</dl>
        </section>
        <section className="doctor-card">
          <h3>Config file</h3>
          <p className="mono doctor-config-path">{report.config_file}</p>
        </section>
      </div>
    </>}
    {!report && !loading && !error && <Empty title="No report yet" copy="Click Recheck to run a live health check." />}
  </div>;
}

function RunTimeline({ profileId, roles }: { profileId: string; roles: Role[] }) {
  const { runs, load } = useProfileRuns(profileId);
  const [selected, setSelected] = useState<string | null>(null);
  const { toolEvents } = useProfileToolEvents(profileId, selected || '');
  const agentName = (id: string) => roles.find(r => r.id === id)?.name || id || 'Default';
  const statusDot = (s: string) => s === 'done' ? 'green' : s === 'failed' ? 'red' : 'yellow';
  return <div className="page">
    <Head title="Run Timeline" copy="Chronological record of every Hermes run across all agents.">
      <button className="button button-outline" onClick={load}><RefreshCw size={14} /> Refresh</button>
    </Head>
    {runs.length === 0
      ? <Empty title="No runs recorded" copy="Runs appear here once Hermes executes a directive or loop." />
      : <div className="timeline-layout">
          <div className="timeline-list">{runs.map(run => <button key={run.id} className={`timeline-row ${selected === run.id ? 'selected' : ''}`} onClick={() => setSelected(selected === run.id ? null : run.id)}>
            <span className={`status-dot ${statusDot(run.status)}`} />
            <div className="timeline-row-body">
              <strong>{agentName(run.agent_id)}</strong>
              <p className="timeline-preview">{run.input_preview || '(no preview)'}</p>
              <small className="mono">{run.started_at.slice(0, 19).replace('T', ' ')} · {run.tool_count} tool{run.tool_count !== 1 ? 's' : ''} · {run.status}</small>
            </div>
            <code className="run-id-chip mono">{run.id.slice(0, 8)}</code>
          </button>)}</div>
          {selected && <aside className="timeline-detail">
            <header><strong>Tool calls</strong><span className="mono quiet-badge">{selected.slice(0, 8)}</span></header>
            {toolEvents.length === 0 ? <Empty title="No tool events recorded" copy="Tool events are recorded when the bridge receives them." /> : toolEvents.map(te => <div key={te.id} className={`tool-event-row ${te.status}`}>
              <span className={`tool-status-badge ${te.status}`}>{te.status === 'ok' ? <Check size={11} /> : <X size={11} />}</span>
              <code>{te.tool_name}</code>
              <span className="tool-duration">{te.duration_ms}ms</span>
            </div>)}
          </aside>}
        </div>}
  </div>;
}

function ScheduleView({ profileId, roles, gateway }: { profileId: string; roles: Role[]; gateway: Gateway }) {
  const { directives, createDirective, updateDirective, deleteDirective } = useScheduledDirectives(profileId);
  const [form, setForm] = useState(false);
  const [directive, setDirective] = useState(''), [agentId, setAgentId] = useState(''), [interval, setInterval] = useState(3600);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');

  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); if (!directive.trim()) return;
    setBusy(true); setError('');
    try { await createDirective(agentId, directive, interval); setDirective(''); setAgentId(''); setInterval(3600); setForm(false); }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not save directive.'); }
    finally { setBusy(false); }
  };

  return <div className="page">
    <Head title="Schedule" copy="Directives that run automatically at a configured interval.">
      <button className="button button-secondary" onClick={() => setForm(v => !v)}><Plus size={14} /> New directive</button>
    </Head>
    {form && <form className="schedule-form" onSubmit={submit}>
      <label>Directive<textarea value={directive} onChange={e => setDirective(e.target.value)} rows={3} placeholder="What should the agent do on each run?" required /></label>
      <label>Agent<select value={agentId} onChange={e => setAgentId(e.target.value)}><option value="">Default (no specific agent)</option>{roles.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}</select></label>
      <label>Interval (seconds)<input type="number" min={60} max={604800} value={interval} onChange={e => setInterval(Number(e.target.value))} /></label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions"><button className="button button-primary" type="submit" disabled={busy}>{busy ? 'Saving...' : 'Save directive'}</button><button className="button button-quiet" type="button" onClick={() => setForm(false)}>Cancel</button></div>
    </form>}
    {gateway.status !== 'online' && <div className="form-error">Hermes is offline — scheduled directives will not fire until the runtime is online.</div>}
    {directives.length === 0 && !form
      ? <Empty title="No scheduled directives" copy="Add a directive and it will fire automatically at the configured interval." />
      : <div className="schedule-list">{directives.map(d => {
          const agent = roles.find(r => r.id === d.agent_id);
          return <div key={d.id} className={`schedule-card ${d.enabled ? '' : 'disabled'}`}>
            <div className="schedule-card-head">
              <span className="quiet-badge">{agent?.name || 'Default agent'}</span>
              <span className="quiet-badge">{d.interval_seconds >= 3600 ? `${Math.round(d.interval_seconds / 3600)}h` : `${Math.round(d.interval_seconds / 60)}m`}</span>
              <span className={`status-dot ${d.enabled ? 'green' : 'idle'}`} />
            </div>
            <p className="schedule-directive">{d.directive}</p>
            {d.last_run_at && <small className="mono">Last run: {d.last_run_at.slice(0, 19).replace('T', ' ')}</small>}
            {d.last_error && <p className="form-error schedule-error">{d.last_error}</p>}
            <div className="schedule-card-actions">
              <button className="button button-quiet" onClick={() => updateDirective(d.id, { enabled: !d.enabled })}>{d.enabled ? 'Pause' : 'Enable'}</button>
              <button className="button button-quiet danger" onClick={() => deleteDirective(d.id)}>Delete</button>
            </div>
          </div>;
        })}</div>}
  </div>;
}

function SettingsView({ gateway, refresh, configure, job }: { gateway: Gateway; refresh: () => void; configure: () => void; job: () => void }) { const [tab, setTab] = useState('Connections'); const tabs = ['Connections','Organisation','Models','Security','Appearance']; const models = count(gateway.models, ['data','models']), jobs = count(gateway.jobs, ['data','jobs']); return <div className="page"><Head title="Settings" copy="Configure infrastructure and inspect what is actually available." /><div className="settings-layout"><nav className="settings-nav">{tabs.map(v => <button key={v} className={tab === v ? 'active' : ''} onClick={() => setTab(v)}>{v}</button>)}</nav><section className="settings-content"><Panel title={tab} subtitle={tab === 'Connections' ? 'Credentials remain server-side' : 'Command-centre preferences'} />{tab === 'Connections' && <><Connection icon={Network} title="Hermes Gateway" detail={gateway.base_url || 'Required for profiles, messages, events, and jobs'} state={statusText(gateway)} action={configure} /><Connection icon={Zap} title="Background jobs" detail="Hermes Jobs API enables scheduled unattended work" state={jobs === null ? 'Not observed' : `${jobs} configured`} action={job} disabled={gateway.status !== 'online'} /><div className="settings-actions"><button className="button button-outline" onClick={refresh}><RefreshCw size={14} /> Recheck connection</button></div></>}{tab === 'Organisation' && <Empty title="Organisation mapping is local" copy="Planned roles persist in this browser; discovered profiles come from Hermes." />}{tab === 'Models' && <Empty title={models === null ? 'No models observed' : `${models} models observed`} copy="Connect Hermes to discover current routes." />}{tab === 'Security' && <div className="settings-copy"><ShieldCheck size={18} /><h3>Server-side credentials</h3><p>The browser never receives HERMES_API_KEY. Put it in the server environment and restart the bridge.</p></div>}{tab === 'Appearance' && <div className="settings-copy"><h3>Quiet command centre</h3><p>The theme follows the project design system and reduced-motion preference.</p></div>}</section></div></div>; }
function Connection({ icon: Icon, title, detail, state, action, disabled }: { icon: React.ElementType; title: string; detail: string; state: string; action: () => void; disabled?: boolean }) { return <div className="connection-row"><span className="source-icon"><Icon size={16} /></span><div><strong>{title}</strong><small>{detail}</small></div><span className="connection-status"><span className="status-dot idle" /> {state}</span><button className="button button-outline" onClick={action} disabled={disabled}>Configure</button></div>; }

function AgentPanel({ profileId, gateway, events, close }: { profileId: string; gateway: Gateway; events: Event[]; close: () => void }) {
  const [small, setSmall] = useState(false), [showTool, setShowTool] = useState<number | null>(null);
  const latestRunData = events.find(e => e.type === 'run.created')?.data;
  const latestRunId = latestRunData && typeof latestRunData.run === 'object' && latestRunData.run !== null
    ? (latestRunData.run as Record<string, unknown>).run_id as string | undefined
    : undefined;
  const { toolEvents } = useProfileToolEvents(profileId, latestRunId || '');
  const toolIcon = (status: string) => status === 'ok' ? <Check size={11} /> : <X size={11} />;
  return <section className={`agent-panel ${small ? 'minimized' : ''}`}>
    <header><span>Agent activity</span><span className="quiet-badge mono">{gateway.status.toUpperCase()}</span><div className="agent-panel-actions"><button className="icon-button" onClick={() => setSmall(v => !v)} aria-label="Minimize"><Minimize2 size={13} /></button><button className="icon-button" onClick={close} aria-label="Close"><X size={14} /></button></div></header>
    {!small && <>
      <div className="agent-panel-body">
        <div className="agent-event"><span className={`status-dot ${tone(gateway)}`} /><div><strong>{gateway.status === 'online' ? 'Hermes connected' : 'Waiting for Hermes'}</strong><p>{gateway.error || (events[0] ? `Latest: ${events[0].type}` : 'No verified activity received.')}</p></div></div>
        {toolEvents.length > 0
          ? <div className="agent-tool-log">{toolEvents.slice(0, 8).map(te => <div key={te.id} className={`tool-event-row ${te.status}`} onClick={() => setShowTool(showTool === te.id ? null : te.id)}>
              <span className={`tool-status-badge ${te.status}`}>{toolIcon(te.status)}</span>
              <code className="tool-name">{te.tool_name}</code>
              <span className="tool-duration">{te.duration_ms}ms</span>
              {showTool === te.id && <div className="tool-evidence"><pre>{JSON.stringify(te.input, null, 2)}</pre><hr /><pre>{JSON.stringify(te.output, null, 2)}</pre></div>}
            </div>)}</div>
          : <div className="agent-log mono">{events.slice(0, 3).map((e, i) => <code key={i}>{e.type}</code>)}{!events.length && <code>No tool calls observed</code>}</div>}
      </div>
      <footer><ChevronRight size={13} /><span>{toolEvents.length > 0 ? `${toolEvents.length} tool calls` : `${events.length} observed events`}</span></footer>
    </>}
  </section>;
}
function Palette({ profileId, close, select }: { profileId: string; close: () => void; select: (v: View) => void }) {
  const [q, setQ] = useState('');
  const [msgResults, setMsgResults] = useState<import('./lib/profile-api').Message[]>([]);
  const navItems = [...nav, { id: 'settings' as View, label: 'Settings', icon: Settings }].filter(i => i.label.toLowerCase().includes(q.toLowerCase()));
  useEffect(() => {
    if (!q.trim() || q.length < 2) { setMsgResults([]); return; }
    const timer = setTimeout(() => {
      searchMessages(profileId, q).then(setMsgResults).catch(() => setMsgResults([]));
    }, 220);
    return () => clearTimeout(timer);
  }, [q, profileId]);
  return <div className="modal-backdrop" onMouseDown={close}>
    <section className="command-palette" role="dialog" aria-modal="true" onMouseDown={e => e.stopPropagation()}>
      <label><Search size={16} /><input autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder="Go to a view or search messages..." /></label>
      <div>
        {navItems.map(i => { const Icon = i.icon; return <button key={i.id} onClick={() => select(i.id)}><Icon size={15} /><span>{i.label}</span><ChevronRight size={13} /></button>; })}
        {msgResults.length > 0 && <>
          <div className="palette-section-label">Messages</div>
          {msgResults.slice(0, 6).map(m => <button key={m.id} onClick={() => { select('messages'); close(); }} className="palette-msg-result">
            <MessageSquare size={14} />
            <span className="palette-msg-text">{m.text.slice(0, 80)}{m.text.length > 80 ? '...' : ''}</span>
            <span className="quiet-badge">{m.direction}</span>
          </button>)}
        </>}
        {!navItems.length && !msgResults.length && <Empty title="No results" copy="Try another view name or message phrase." />}
      </div>
    </section>
  </div>;
}
function Popover({ title, children, close }: { title: string; children: React.ReactNode; close: () => void }) { return <aside className="app-popover"><header><strong>{title}</strong><button className="icon-button" onClick={close} aria-label="Close"><X size={14} /></button></header>{children}</aside>; }
function Empty({ title, copy }: { title: string; copy: string }) { return <div className="compact-empty"><strong>{title}</strong><p>{copy}</p></div>; }

function Dialog({ kind, profileId, roles, gateway, close, task, role, source, configure, run, job }: { kind: Exclude<Kind,null>; profileId: string; roles: Role[]; gateway: Gateway; close: () => void; task: (v: Task) => void; role: (v: Role) => void; source: (v: Source) => void; configure: (v: string) => Promise<void>; run: (v: string,s: string) => Promise<unknown>; job: (v: Record<string,string>) => Promise<unknown> }) {
  const [a, setA] = useState(kind === 'connection' ? gateway.base_url || '' : ''), [b, setB] = useState(''), [schedule, setSchedule] = useState('0 9 * * 1-5'), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [selectedAgents, setSelectedAgents] = useState<string[]>([]);
  const [groupResult, setGroupResult] = useState<GroupRunResult | null>(null);
  const titles = { directive: 'New directive', task: 'Add local task', role: 'Add planned role', group: 'Group directive', source: 'Add source plan', connection: 'Connect Hermes Gateway', job: 'Create background job' };
  const submit = async (e: FormEvent) => {
    e.preventDefault(); if (!a.trim()) return setError('This field is required.'); setBusy(true); setError('');
    try {
      if (kind === 'connection') await configure(a.trim());
      else if (kind === 'directive') await run(a.trim(), 'jarvis-ceo');
      else if (kind === 'job') await job({ prompt: a.trim(), schedule: schedule.trim() });
      else if (kind === 'task') task({ id: crypto.randomUUID(), title: a.trim(), area: b.trim() || 'General', state: 'draft' });
      else if (kind === 'group') {
        if (!profileId || gateway.status !== 'online') throw new Error('Hermes must be online to send a group directive.');
        const agentIds = selectedAgents.length > 0 ? selectedAgents : roles.map(r => r.id);
        const result = await createGroupRun(profileId, agentIds, a.trim());
        setGroupResult(result); setBusy(false); return;
      } else if (kind === 'role') role({ id: crypto.randomUUID(), name: a.trim(), role: b.trim() || 'Planned role', initials: a.trim().split(/\s+/).map(x => x[0]).join('').slice(0,2).toUpperCase() });
      else source({ id: crypto.randomUUID(), title: a.trim(), detail: b.trim() || 'Not configured' });
      close();
    } catch (e) { setError(e instanceof Error ? e.message : 'Action failed.'); } finally { setBusy(false); }
  };
  const remote = kind === 'directive' || kind === 'job' || kind === 'group';
  if (groupResult) return <div className="modal-backdrop" onMouseDown={close}><section className="action-dialog" role="dialog" aria-modal="true" onMouseDown={e => e.stopPropagation()}><header><div><h2>Group directive sent</h2></div><button type="button" className="icon-button" onClick={close}><X size={15} /></button></header><div className="group-run-results">{groupResult.runs.map((r, i) => { const agentName = roles.find(x => x.id === r.agent_id)?.name || r.agent_id || 'Agent'; return <div key={i} className={`group-run-row ${r.status}`}><span className={`status-dot ${r.status === 'started' ? 'green' : 'red'}`} /><strong>{agentName}</strong>{r.run_id && <code className="mono">{r.run_id.slice(0, 8)}</code>}{r.error && <span className="form-error">{r.error}</span>}</div>; })}</div><footer><button className="button button-outline" onClick={close}>Done</button></footer></section></div>;
  return <div className="modal-backdrop" onMouseDown={close}><form className="action-dialog" role="dialog" aria-modal="true" onMouseDown={e => e.stopPropagation()} onSubmit={submit}><header><div><h2>{titles[kind]}</h2><p>{kind === 'connection' ? 'The endpoint is saved by the server; the API key stays in its environment.' : remote ? 'This creates a real Hermes operation and requires an online gateway.' : 'This item is saved locally in your browser.'}</p></div><button type="button" className="icon-button" onClick={close}><X size={15} /></button></header><label><span>{kind === 'connection' ? 'Gateway URL' : kind === 'job' ? 'Job prompt' : kind === 'directive' ? 'Directive' : kind === 'role' ? 'Role name' : kind === 'group' ? 'Directive to fan out' : kind === 'source' ? 'Source name' : 'Task title'}</span>{remote ? <textarea autoFocus value={a} onChange={e => setA(e.target.value)} maxLength={12000} rows={5} /> : <input autoFocus value={a} onChange={e => setA(e.target.value)} maxLength={200} placeholder={kind === 'connection' ? 'http://127.0.0.1:8642' : ''} />}</label>{kind === 'group' && roles.length > 0 && <div className="group-agent-picker"><span>Send to (leave empty for all)</span>{roles.map(r => <label key={r.id} className="group-agent-option"><input type="checkbox" checked={selectedAgents.includes(r.id)} onChange={e => setSelectedAgents(prev => e.target.checked ? [...prev, r.id] : prev.filter(x => x !== r.id))} />{r.name}</label>)}</div>}{['task','role','source'].includes(kind) && <label><span>{kind === 'task' ? 'Area' : kind === 'role' ? 'Responsibility' : 'Connection note'}</span><input value={b} onChange={e => setB(e.target.value)} maxLength={300} /></label>}{kind === 'job' && <label><span>Cron schedule</span><input value={schedule} onChange={e => setSchedule(e.target.value)} /><small>Example: 0 9 * * 1-5 runs at 9:00 on weekdays.</small></label>}{error && <div className="form-error" role="alert">{error}</div>}<footer><button type="button" className="button button-outline" onClick={close}>Cancel</button><button className="button button-primary" disabled={busy || (remote && gateway.status !== 'online')}>{busy ? 'Working...' : kind === 'connection' ? 'Connect and verify' : kind === 'group' ? 'Send to all agents' : kind === 'job' ? 'Create job' : 'Save'}</button></footer></form></div>;
}

function AutonomyControl({ mode, setMode }: { mode: ApprovalMode; setMode: (mode: ApprovalMode) => void }) { const enabled = mode === 'auto_safe'; return <section className="autonomy-control" aria-labelledby="autonomy-title"><div className="autonomy-control-heading"><span className={`autonomy-mark ${enabled ? 'enabled' : ''}`}><Sparkles size={18} /></span><div><h2 id="autonomy-title">Approve for me</h2><p>{enabled ? 'Routine work runs without interrupting you.' : 'Require approval before agent actions.'}</p></div><button className={`toggle-control ${enabled ? 'enabled' : ''}`} role="switch" aria-checked={enabled} onClick={() => setMode(enabled ? 'manual' : 'auto_safe')}><span /></button></div><div className="autonomy-control-scope"><strong>Runs automatically</strong><span>Reading configured knowledge, drafting, and reversible local work.</span><strong>Still asks first</strong><span>Messages, account creation, spending, publishing, deletion, credentials, security, and other irreversible actions.</span></div><div className="terminal-command-panel"><div><span className="mono">RUNTIME COMMANDS</span><h3>Configure from Terminal</h3><p>Use these commands with the OrbityLabs desktop runtime.</p></div><pre><code>{`orbitylabs models add &lt;provider/model&gt;\norbitylabs config set autonomy ${enabled ? 'auto-safe' : 'manual'}\norbitylabs config list`}</code></pre></div></section>; }
