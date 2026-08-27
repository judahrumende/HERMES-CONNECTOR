import React, { useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Activity, AlertCircle, ArrowRight, Bell, Bot, Check, ChevronDown, ChevronLeft,
  ChevronRight, Circle, Clock3, Command, CornerDownLeft, Database, FileText,
  GitBranch, Inbox, LayoutDashboard, Link2, ListFilter, MessageSquare,
  Minimize2, MoreHorizontal, Network, Paperclip, Plus, Search, Send, Settings,
  ShieldCheck, SlidersHorizontal, Sparkles, Users, X, Zap,
} from 'lucide-react';
import './linear.css';
import FinishedApp from './finished-app';

type View = 'overview' | 'messages' | 'work' | 'agents' | 'knowledge' | 'approvals' | 'settings';
type Status = 'live' | 'idle' | 'blocked' | 'draft';
type Conversation = { id: string; name: string; role: string; preview: string; initials: string; status: Status };

const conversations: Conversation[] = [
  { id: 'ceo', name: 'CEO', role: 'Strategic orchestrator', preview: 'Ready for a directive', initials: 'HJ', status: 'idle' },
  { id: 'chief', name: 'Chief of Staff', role: 'Operations', preview: 'Hermes connection required', initials: 'CS', status: 'idle' },
  { id: 'research', name: 'Research room', role: 'Group conversation', preview: 'No connected members', initials: 'RR', status: 'idle' },
  { id: 'growth', name: 'Growth', role: 'Department', preview: 'No current activity', initials: 'GR', status: 'idle' },
];

const navItems: Array<{ id: View; label: string; icon: React.ElementType }> = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'messages', label: 'Messages', icon: MessageSquare },
  { id: 'work', label: 'Work', icon: Inbox },
  { id: 'agents', label: 'Agents', icon: Bot },
  { id: 'knowledge', label: 'Knowledge', icon: Database },
  { id: 'approvals', label: 'Approvals', icon: ShieldCheck },
];

function App() {
  const [inside, setInside] = useState(false);
  return inside ? <CommandCentre /> : <LandingPage onEnter={() => setInside(true)} />;
}

function Brand({ compact = false }: { compact?: boolean }) {
  return <span className="brand-lockup"><span className="brand-mark" aria-hidden="true"><i /><i /><i /></span>{!compact && <span>Hermes Jarvis</span>}</span>;
}

function LandingPage({ onEnter }: { onEnter: () => void }) {
  const desktopDownload = 'https://github.com/judahrumende/hermes-jarvis/releases/latest/download/Hermes%20Jarvis-1.0.0-arm64.dmg';
  return (
    <div className="landing">
      <header className="site-nav">
        <Brand />
        <nav aria-label="Primary navigation"><a href="#system">System</a><a href="#architecture">Architecture</a><a href="#control">Human control</a></nav>
        <button className="button button-primary" onClick={onEnter}>Open command centre <ArrowRight size={14} /></button>
      </header>
      <main>
        <section className="hero">
          <div className="hero-copy">
            <h1>The operating system for an autonomous AI organisation.</h1>
            <p>Persistent agents, visible work, and human authority—assembled into one command centre.</p>
            <div className="hero-actions"><button className="button button-secondary" onClick={onEnter}>Explore the interface <ArrowRight size={14} /></button><a href={desktopDownload} className="text-link">Download for Mac <ArrowRight size={14} /></a><a href="#system" className="text-link">See the system <ChevronDown size={14} /></a></div>
          </div>
          <div className="hero-stage" id="system"><ProductScene /></div>
        </section>

        <section className="statement-section" id="architecture">
          <h2><strong>One organisation, not a collection of chats.</strong> Durable roles, shared context, directed work, and explicit escalation form a system that can keep operating beyond one browser window.</h2>
          <div className="architecture-grid">
            <ArchitectureFigure type="profiles" title="Persistent profiles" text="Specialised roles retain identity and responsibility across sessions once Hermes is connected." />
            <ArchitectureFigure type="work" title="Directed work" text="Objectives move through visible queues, owners, dependencies, and review boundaries." />
            <ArchitectureFigure type="authority" title="Human authority" text="Approvals and high-impact actions return to an operator with the context needed to decide." />
          </div>
        </section>

        <section className="control-section" id="control">
          <div className="control-copy"><h2>Complex work should remain legible.</h2><p>Hermes Jarvis is designed to show the organisation as it is: what is connected, what is waiting, where work sits, and which decisions still belong to a person.</p><button className="button button-outline" onClick={onEnter}>Inspect the command centre <ArrowRight size={14} /></button></div>
          <WorkflowPreview />
        </section>
      </main>
      <footer className="site-footer"><Brand /><span>Autonomous work, made legible.</span><span className="mono">Connect: npm run hermes:connect -- http://127.0.0.1:8642</span><a className="mono" href={desktopDownload}>Download desktop · macOS arm64</a></footer>
    </div>
  );
}

function ProductScene() {
  return (
    <div className="product-scene" aria-label="Hermes Jarvis command centre preview">
      <aside className="scene-sidebar">
        <div className="scene-workspace"><span className="avatar avatar-accent">H</span><span>Jarvis HQ</span><ChevronDown size={12} /></div>
        <div className="scene-command"><Search size={12} /><span>Search</span><kbd>⌘ K</kbd></div>
        <SceneGroup label="Workspace"><span className="scene-nav active"><LayoutDashboard size={13} /> Overview</span><span className="scene-nav"><Inbox size={13} /> Work</span><span className="scene-nav"><Bot size={13} /> Agents</span><span className="scene-nav"><Database size={13} /> Knowledge</span></SceneGroup>
        <SceneGroup label="Attention"><span className="scene-nav"><AlertCircle size={13} /> Setup required</span><span className="scene-nav"><ShieldCheck size={13} /> Approvals</span></SceneGroup>
        <div className="scene-offline"><span className="status-dot idle" /> Hermes offline</div>
      </aside>
      <div className="scene-content">
        <div className="scene-toolbar"><span>Organisation overview</span><div><Search size={13} /><Bell size={13} /><MoreHorizontal size={14} /></div></div>
        <div className="scene-body">
          <div className="scene-title"><div><h3>Operating picture</h3><p>Local interface state · no live organisation data</p></div><span className="quiet-badge">Not configured</span></div>
          <div className="scene-status-grid"><SceneStatus icon={Network} title="Hermes Gateway" detail="Connection required" status="blocked" /><SceneStatus icon={Users} title="Profiles" detail="Sync unavailable" status="idle" /><SceneStatus icon={Zap} title="Workers" detail="No runtime connected" status="idle" /></div>
          <div className="scene-split">
            <section className="scene-panel work-panel"><header><span>Work queue</span><span className="panel-tools"><ListFilter size={12} /><MoreHorizontal size={13} /></span></header><div className="work-group"><span><Circle size={11} /> Setup</span><span>Required</span></div><SceneTask title="Connect Hermes Gateway" meta="Infrastructure" status="blocked" /><SceneTask title="Review approval boundaries" meta="Governance" status="draft" /><div className="work-group muted"><span><Check size={11} /> Complete</span><span>None</span></div></section>
            <section className="scene-panel activity-panel"><header><span>Activity</span><Clock3 size={12} /></header><div className="activity-empty"><Activity size={16} /><strong>No organisation events</strong><p>Connected agent and work events will appear here.</p></div></section>
          </div>
        </div>
      </div>
      <aside className="scene-inspector"><header><span>Setup detail</span><X size={13} /></header><div className="inspector-title"><span className="avatar">HG</span><div><strong>Hermes Gateway</strong><small>Required connection</small></div></div><dl><div><dt>Status</dt><dd><span className="status-dot blocked" /> Not configured</dd></div><div><dt>Endpoint</dt><dd className="mono">Not provided</dd></div><div><dt>Authentication</dt><dd>Unavailable</dd></div><div><dt>Last check</dt><dd>Never</dd></div></dl><div className="inspector-note"><ShieldCheck size={14} /><p>Credentials remain server-side when a connector is configured.</p></div></aside>
      <AgentPanel preview />
    </div>
  );
}

function SceneGroup({ label, children }: { label: string; children: React.ReactNode }) { return <div className="scene-group"><span className="scene-group-label">{label}</span>{children}</div>; }
function SceneStatus({ icon: Icon, title, detail, status }: { icon: React.ElementType; title: string; detail: string; status: Status }) { return <div className="scene-status"><span className="scene-status-icon"><Icon size={14} /></span><div><strong>{title}</strong><small>{detail}</small></div><span className={`status-dot ${status}`} /></div>; }
function SceneTask({ title, meta, status }: { title: string; meta: string; status: Status }) { return <div className="scene-task"><span className={`task-state ${status}`} /><div><strong>{title}</strong><small>{meta}</small></div><ChevronRight size={12} /></div>; }

function ArchitectureFigure({ type, title, text }: { type: 'profiles' | 'work' | 'authority'; title: string; text: string }) {
  return <article className="architecture-card"><span className="mono architecture-label">{title.toUpperCase()}</span><div className={`architecture-visual ${type}`} aria-hidden="true"><span className="architecture-core" /><span className="architecture-node node-one" /><span className="architecture-node node-two" /><span className="architecture-node node-three" /><span className="architecture-path path-one" /><span className="architecture-path path-two" /></div><h3>{title}</h3><p>{text}</p></article>;
}

function WorkflowPreview() {
  return <div className="workflow-preview"><header><span>Decision flow</span><span className="quiet-badge">Example structure</span></header><WorkflowRow icon={Command} title="Operator directive" text="Purpose and constraints enter the organisation." state="Human" /><div className="workflow-connector" /><WorkflowRow icon={Bot} title="CEO decomposition" text="Work is routed to the appropriate specialised role." state="Agent" /><div className="workflow-connector" /><WorkflowRow icon={ShieldCheck} title="Approval boundary" text="High-impact actions return with evidence and context." state="Review" /></div>;
}
function WorkflowRow({ icon: Icon, title, text, state }: { icon: React.ElementType; title: string; text: string; state: string }) { return <div className="workflow-row"><span className="flow-icon"><Icon size={14} /></span><div><strong>{title}</strong><small>{text}</small></div><span className="flow-state">{state}</span></div>; }

function CommandCentre() {
  const [view, setView] = useState<View>('overview');
  const [agentPanelOpen, setAgentPanelOpen] = useState(() => typeof window !== 'undefined' && !window.matchMedia('(max-width: 720px)').matches);
  return (
    <div className="command-app">
      <aside className="app-sidebar">
        <button className="workspace-switcher"><span className="avatar avatar-accent">H</span><span><strong>Jarvis HQ</strong><small>Local workspace</small></span><ChevronDown size={13} /></button>
        <button className="command-search"><Search size={14} /><span>Search</span><kbd>⌘ K</kbd></button>
        <nav aria-label="Command centre"><span className="nav-label">Workspace</span>{navItems.map(item => <AppNavItem key={item.id} item={item} active={view === item.id} onClick={() => setView(item.id)} />)}<span className="nav-label nav-label-spaced">System</span><AppNavItem item={{ id: 'settings', label: 'Settings', icon: Settings }} active={view === 'settings'} onClick={() => setView('settings')} /></nav>
        <div className="sidebar-spacer" /><div className="sidebar-connection"><span className="status-dot idle" /><div><strong>Hermes offline</strong><small>Connector not configured</small></div></div><button className="button button-primary sidebar-primary"><Plus size={14} /> New directive</button>
      </aside>
      <main className="app-main"><header className="app-topbar"><div className="breadcrumbs"><span>Jarvis HQ</span><ChevronRight size={12} /><strong>{viewLabel(view)}</strong></div><div className="topbar-actions"><button className="icon-button" aria-label="Search"><Search size={15} /></button><button className="icon-button" aria-label="Notifications"><Bell size={15} /></button><button className="button button-quiet" onClick={() => setAgentPanelOpen(true)}><Sparkles size={14} /> Agent activity</button><button className="avatar user-avatar" aria-label="Account">JR</button></div></header><div className="app-view">{view === 'overview' && <OverviewView setView={setView} />}{view === 'messages' && <MessagesView />}{view === 'work' && <WorkView />}{view === 'agents' && <AgentsView />}{view === 'knowledge' && <KnowledgeView />}{view === 'approvals' && <ApprovalsView />}{view === 'settings' && <SettingsView />}</div></main>
      <nav className="mobile-app-nav" aria-label="Mobile command centre">
        {navItems.slice(0, 4).map(item => { const Icon = item.icon; return <button key={item.id} className={view === item.id ? 'active' : ''} onClick={() => setView(item.id)}><Icon size={16} /><span>{item.label}</span></button>; })}
        <button className={view === 'settings' ? 'active' : ''} onClick={() => setView('settings')}><Settings size={16} /><span>More</span></button>
      </nav>
      {agentPanelOpen && <AgentPanel onClose={() => setAgentPanelOpen(false)} />}
    </div>
  );
}

function AppNavItem({ item, active, onClick }: { item: { id: View; label: string; icon: React.ElementType }; active: boolean; onClick: () => void }) { const Icon = item.icon; return <button className={`app-nav-item ${active ? 'active' : ''}`} onClick={onClick}><Icon size={15} /><span>{item.label}</span>{item.id === 'approvals' && <span className="nav-meta">—</span>}</button>; }
function viewLabel(view: View) { return navItems.find(item => item.id === view)?.label ?? 'Settings'; }
function PageHeader({ title, copy, children }: { title: string; copy: string; children?: React.ReactNode }) { return <header className="page-header"><div><h1>{title}</h1><p>{copy}</p></div>{children && <div className="page-actions">{children}</div>}</header>; }

function OverviewView({ setView }: { setView: (view: View) => void }) {
  return <div className="page overview-page"><PageHeader title="Organisation overview" copy="A truthful operating picture of the local interface and its unconfigured services."><button className="button button-outline"><SlidersHorizontal size={14} /> Configure view</button><button className="button button-secondary" onClick={() => setView('messages')}>Message CEO <ArrowRight size={14} /></button></PageHeader><div className="system-strip"><SystemStripItem icon={Network} label="Gateway" value="Not configured" status="blocked" /><SystemStripItem icon={Users} label="Profiles" value="Sync unavailable" status="idle" /><SystemStripItem icon={Zap} label="Workers" value="No runtime" status="idle" /><SystemStripItem icon={Database} label="Knowledge" value="No sources" status="idle" /></div><div className="dashboard-grid">
    <section className="dashboard-panel work-queue-panel"><PanelHeader title="Work queue" subtitle="Configuration work only" actions={<><button className="icon-button" aria-label="Filter work"><ListFilter size={14} /></button><button className="icon-button" aria-label="Work menu"><MoreHorizontal size={15} /></button></>} /><div className="queue-columns"><QueueColumn title="Required" status="blocked"><WorkCard title="Connect Hermes Gateway" team="Infrastructure" status="blocked" /><WorkCard title="Choose persistent storage" team="Architecture" status="draft" /></QueueColumn><QueueColumn title="Review" status="draft"><WorkCard title="Define approval boundaries" team="Governance" status="draft" /></QueueColumn><QueueColumn title="Complete" status="idle"><EmptyQueue /></QueueColumn></div></section>
    <section className="dashboard-panel attention-panel"><PanelHeader title="Attention" subtitle="What needs an operator" /><AttentionRow icon={AlertCircle} title="Hermes Gateway" detail="URL and credentials required" tone="blocked" /><AttentionRow icon={Users} title="Profile synchronisation" detail="Waiting for a connection" tone="idle" /><AttentionRow icon={ShieldCheck} title="Pending approvals" detail="Nothing requires review" tone="idle" /><button className="panel-link" onClick={() => setView('settings')}>Open connection settings <ArrowRight size={13} /></button></section>
    <section className="dashboard-panel activity-feed-panel"><PanelHeader title="Organisation activity" subtitle="Events from agents, tools, and work" actions={<button className="button button-quiet"><ListFilter size={13} /> Filter</button>} /><div className="empty-activity"><span className="empty-activity-line" /><span className="empty-activity-icon"><Activity size={16} /></span><div><strong>No live events yet</strong><p>When Hermes is connected, agent decisions, tool calls, handoffs, and work transitions will be recorded here.</p></div></div><div className="activity-schema"><span>Event</span><span>Actor</span><span>Context</span><span>Time</span></div></section>
    <section className="dashboard-panel roster-panel"><PanelHeader title="Agent roster" subtitle="Planned organisation roles" actions={<button className="icon-button" aria-label="Agent roster menu"><MoreHorizontal size={15} /></button>} /><AgentRow initials="HJ" name="CEO" role="Strategy and orchestration" /><AgentRow initials="CS" name="Chief of Staff" role="Operations and follow-through" /><AgentRow initials="RR" name="Research" role="Evidence and synthesis" /><button className="panel-link" onClick={() => setView('agents')}>View organisation <ArrowRight size={13} /></button></section>
  </div></div>;
}

function SystemStripItem({ icon: Icon, label, value, status }: { icon: React.ElementType; label: string; value: string; status: Status }) { return <div className="system-strip-item"><span className="strip-icon"><Icon size={14} /></span><div><span>{label}</span><strong>{value}</strong></div><span className={`status-dot ${status}`} /></div>; }
function PanelHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: React.ReactNode }) { return <header className="panel-header"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>{actions && <div className="panel-actions">{actions}</div>}</header>; }
function QueueColumn({ title, status, children }: { title: string; status: Status; children: React.ReactNode }) { return <div className="queue-column"><header><span><span className={`status-ring ${status}`} />{title}</span><span><Plus size={13} /><MoreHorizontal size={14} /></span></header>{children}</div>; }
function WorkCard({ title, team, status }: { title: string; team: string; status: Status }) { return <article className="work-card"><div><span className={`task-state ${status}`} /><strong>{title}</strong></div><footer><span className="quiet-badge">{team}</span><span className="avatar avatar-xs">—</span></footer></article>; }
function EmptyQueue() { return <div className="empty-queue"><Check size={14} /><span>No completed work</span></div>; }
function AttentionRow({ icon: Icon, title, detail, tone }: { icon: React.ElementType; title: string; detail: string; tone: Status }) { return <div className="attention-row"><span className={`attention-icon ${tone}`}><Icon size={14} /></span><div><strong>{title}</strong><small>{detail}</small></div><ChevronRight size={13} /></div>; }
function AgentRow({ initials, name, role }: { initials: string; name: string; role: string }) { return <div className="agent-row"><span className="avatar">{initials}</span><div><strong>{name}</strong><small>{role}</small></div><span className="agent-state"><span className="status-dot idle" /> Offline</span></div>; }

function MessagesView() {
  const [activeId, setActiveId] = useState('ceo'); const [mobileChatOpen, setMobileChatOpen] = useState(false); const [draft, setDraft] = useState(''); const [sent, setSent] = useState<string[]>([]);
  const active = useMemo(() => conversations.find(item => item.id === activeId) ?? conversations[0], [activeId]);
  const send = () => { const next = draft.trim(); if (!next) return; setSent(current => [...current, next]); setDraft(''); };
  return <div className={`messages-layout ${mobileChatOpen ? 'mobile-thread-open' : ''}`}><aside className="conversation-pane"><header><div><h1>Conversations</h1><p>Local presentation state</p></div><button className="icon-button" aria-label="Conversation menu"><MoreHorizontal size={16} /></button></header><label className="search-field"><Search size={14} /><input aria-label="Search conversations" placeholder="Search conversations" /></label><div className="conversation-list">{conversations.map(item => <button key={item.id} className={`conversation-row ${activeId === item.id ? 'selected' : ''}`} onClick={() => { setActiveId(item.id); setMobileChatOpen(true); }}><span className="avatar">{item.initials}</span><span><strong>{item.name}</strong><small>{item.role}</small><em>{item.preview}</em></span><span className={`status-dot ${item.status}`} /></button>)}</div><button className="button button-outline new-conversation"><Plus size={14} /> New conversation</button></aside><section className="thread-pane"><header className="thread-header"><div><button className="icon-button mobile-back" aria-label="Back to conversations" onClick={() => setMobileChatOpen(false)}><ChevronLeft size={16} /></button><span className="avatar">{active.initials}</span><span><strong>{active.name}</strong><small>{active.role} · isolated context</small></span></div><div><button className="icon-button" aria-label="Search thread"><Search size={15} /></button><button className="icon-button" aria-label="Thread menu"><MoreHorizontal size={16} /></button></div></header><div className="thread-stream"><div className="thread-date mono">TODAY</div><Message avatar={active.initials} name={active.name}>The interface is ready. Connect Hermes to begin a real session; no agent response is being simulated.</Message>{sent.map((message, index) => <Message key={`${message}-${index}`} avatar="You" name="You">{message}</Message>)}<InlineConnectionCard /></div><div className="composer-wrap"><div className="composer"><button className="icon-button" aria-label="Attach file"><Paperclip size={15} /></button><textarea value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); send(); } }} placeholder={`Message ${active.name}…`} rows={1} /><button className="send-button" aria-label="Send message" onClick={send} disabled={!draft.trim()}><Send size={14} /></button></div><div className="composer-meta"><span>Connector offline — messages stay in this browser</span><span className="mono"><CornerDownLeft size={11} /> ENTER TO SEND</span></div></div></section><aside className="thread-inspector"><PanelHeader title="Conversation" subtitle="Local metadata" /><dl><div><dt>Context</dt><dd>Isolated</dd></div><div><dt>Members</dt><dd>Not synced</dd></div><div><dt>Transport</dt><dd>Local only</dd></div><div><dt>Encryption</dt><dd>Not configured</dd></div></dl><div className="inspector-note"><ShieldCheck size={14} /><p>No message leaves this browser in the current interface shell.</p></div></aside></div>;
}

function Message({ avatar, name, children }: { avatar: string; name: string; children: React.ReactNode }) { return <div className="message"><span className={`avatar ${name === 'You' ? 'user-message-avatar' : ''}`}>{avatar}</span><div><header><strong>{name}</strong><time>now</time></header><p>{children}</p></div></div>; }
function InlineConnectionCard() { return <div className="inline-connection"><span className="inline-connection-icon"><Network size={15} /></span><div><strong>Hermes Gateway is not connected</strong><p>Agent replies, persistence, profile synchronisation, and tool events remain unavailable.</p></div><button className="button button-outline">Open settings</button></div>; }

function WorkView() { return <div className="page"><PageHeader title="Work" copy="Configuration tasks and future organisation work in one queue."><button className="button button-outline"><ListFilter size={14} /> Filter</button><button className="button button-secondary"><Plus size={14} /> Add local task</button></PageHeader><div className="table-panel"><div className="table-toolbar"><div className="segmented"><button className="active">All work</button><button>Required</button><button>Review</button><button>Complete</button></div><button className="icon-button" aria-label="Work display settings"><SlidersHorizontal size={15} /></button></div><div className="data-table work-table"><div className="table-head"><span>Status</span><span>Task</span><span>Area</span><span>Owner</span><span>Runtime</span><span /></div><WorkTableRow state="blocked" title="Connect Hermes Gateway" area="Infrastructure" /><WorkTableRow state="draft" title="Choose persistent work storage" area="Architecture" /><WorkTableRow state="draft" title="Define approval boundaries" area="Governance" /><WorkTableRow state="idle" title="Synchronise Hermes profiles" area="Organisation" /></div></div></div>; }
function WorkTableRow({ state, title, area }: { state: Status; title: string; area: string }) { return <div className="table-row"><span><span className={`status-ring ${state}`} /> {state === 'blocked' ? 'Required' : state === 'draft' ? 'Draft' : 'Waiting'}</span><strong>{title}</strong><span className="quiet-badge">{area}</span><span>Unassigned</span><span className="mono">Unavailable</span><MoreHorizontal size={15} /></div>; }

function AgentsView() { return <div className="page"><PageHeader title="Agents" copy="The planned organisation structure and current connection state."><button className="button button-outline"><Network size={14} /> Organisation map</button><button className="button button-secondary"><Plus size={14} /> Add planned role</button></PageHeader><div className="agents-layout"><section className="table-panel"><PanelHeader title="Organisation roster" subtitle="No profiles are currently synchronised" /><div className="data-table agent-table"><div className="table-head"><span>Agent</span><span>Role</span><span>Status</span><span>Model</span><span>Workspace</span><span /></div><AgentTableRow initials="HJ" name="CEO" role="Strategy and orchestration" /><AgentTableRow initials="CS" name="Chief of Staff" role="Operations and follow-through" /><AgentTableRow initials="RR" name="Research" role="Evidence and synthesis" /><AgentTableRow initials="GR" name="Growth" role="Distribution and experiments" /></div></section><aside className="detail-panel"><PanelHeader title="Profile sync" subtitle="Hermes connection required" /><div className="setup-sequence"><SetupStep title="Connect Gateway" detail="Provide a server-side endpoint and credential." /><SetupStep title="Discover profiles" detail="Read available Hermes profile metadata." /><SetupStep title="Map organisation" detail="Assign durable roles and reporting lines." /></div></aside></div></div>; }
function AgentTableRow({ initials, name, role }: { initials: string; name: string; role: string }) { return <div className="table-row"><span className="agent-cell"><span className="avatar">{initials}</span><strong>{name}</strong></span><span>{role}</span><span><span className="status-dot idle" /> Offline</span><span className="mono">Not set</span><span>Local plan</span><MoreHorizontal size={15} /></div>; }

function KnowledgeView() { return <div className="page"><PageHeader title="Knowledge" copy="Shared organisational context and planned source connections."><button className="button button-outline"><Search size={14} /> Search knowledge</button><button className="button button-secondary"><Plus size={14} /> Add source</button></PageHeader><div className="knowledge-layout"><section className="table-panel"><PanelHeader title="Sources" subtitle="Nothing is connected" /><KnowledgeRow icon={Database} title="Obsidian vault" detail="Not configured" /><KnowledgeRow icon={GitBranch} title="Graph knowledge" detail="Graphify not configured" /><KnowledgeRow icon={FileText} title="Organisation documents" detail="No storage provider" /></section><aside className="detail-panel"><PanelHeader title="Retrieval policy" subtitle="Unavailable until sources exist" /><dl className="stacked-metadata"><div><dt>Index</dt><dd>Not available</dd></div><div><dt>Embeddings</dt><dd>Not selected</dd></div><div><dt>Access policy</dt><dd>Not defined</dd></div><div><dt>Last sync</dt><dd>Never</dd></div></dl></aside></div></div>; }
function KnowledgeRow({ icon: Icon, title, detail }: { icon: React.ElementType; title: string; detail: string }) { return <div className="knowledge-row"><span className="source-icon"><Icon size={16} /></span><div><strong>{title}</strong><small>{detail}</small></div><span className="quiet-badge">Not configured</span><button className="icon-button" aria-label={`${title} menu`}><MoreHorizontal size={15} /></button></div>; }

function ApprovalsView() { return <div className="page"><PageHeader title="Approvals" copy="High-impact decisions will wait here for explicit human authority."><button className="button button-outline"><SlidersHorizontal size={14} /> Approval policy</button></PageHeader><div className="approvals-shell"><div className="approval-tabs"><button className="active">Pending</button><button>Resolved</button><button>Policy events</button></div><div className="approval-empty"><span className="empty-symbol"><ShieldCheck size={20} /></span><h2>No decisions require approval</h2><p>This is an empty operational state—not evidence that agents are running. Approval requests will appear only after Hermes and a worker runtime are connected.</p><button className="button button-outline">Review planned boundaries</button></div></div></div>; }

function SettingsView() { return <div className="page"><PageHeader title="Settings" copy="Configure the infrastructure required to move beyond the local interface shell." /><div className="settings-layout"><nav className="settings-nav"><button className="active">Connections</button><button>Organisation</button><button>Models</button><button>Security</button><button>Appearance</button></nav><section className="settings-content"><PanelHeader title="Connections" subtitle="External services remain disabled until valid credentials are supplied" /><ConnectionRow icon={Network} title="Hermes Gateway" detail="Required for profiles, messages, and events" /><ConnectionRow icon={Database} title="Persistent storage" detail="Required for durable work and history" /><ConnectionRow icon={Link2} title="Knowledge connectors" detail="Optional shared organisational context" /><ConnectionRow icon={Zap} title="Worker runtime" detail="Required for unattended background execution" /></section></div></div>; }
function ConnectionRow({ icon: Icon, title, detail }: { icon: React.ElementType; title: string; detail: string }) { return <div className="connection-row"><span className="source-icon"><Icon size={16} /></span><div><strong>{title}</strong><small>{detail}</small></div><span className="connection-status"><span className="status-dot idle" /> Not configured</span><button className="button button-outline">Configure</button></div>; }
function SetupStep({ title, detail }: { title: string; detail: string }) { return <div className="setup-step"><span className="setup-index"><Circle size={10} /></span><div><strong>{title}</strong><p>{detail}</p></div></div>; }

function AgentPanel({ preview = false, onClose }: { preview?: boolean; onClose?: () => void }) {
  return <section className={`agent-panel ${preview ? 'agent-panel-preview' : ''}`}><header><span><span className="brand-mark tiny" aria-hidden="true"><i /><i /><i /></span>Agent activity</span><span className="quiet-badge mono">MODEL UNSET</span>{!preview && <div className="agent-panel-actions"><button className="icon-button" aria-label="Minimize agent panel"><Minimize2 size={13} /></button><button className="icon-button" aria-label="Close agent panel" onClick={onClose}><X size={14} /></button></div>}</header><div className="agent-panel-body"><div className="agent-event"><span className="status-dot idle" /><div><strong>Waiting for Hermes</strong><p>Connect a Gateway and worker runtime to begin a real agent session.</p></div></div><div className="agent-log mono"><span>SYSTEM</span><code>No tool calls</code><code>No model selected</code></div></div><footer><ChevronRight size={13} /><span>Worked for 0s</span><span>Local interface state</span></footer></section>;
}

declare global { var __hermesRoot: ReturnType<typeof createRoot> | undefined; }
const root = globalThis.__hermesRoot ?? createRoot(document.getElementById('root')!);
globalThis.__hermesRoot = root;
root.render(<FinishedApp landing={onEnter => <LandingPage onEnter={onEnter} />} />);
