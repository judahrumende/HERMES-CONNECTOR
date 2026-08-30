import React, { FormEvent, useMemo, useState } from 'react';
import { ArrowUpRight, Bot, Check, Download, GitBranch, Link, Send, ShieldCheck, Sparkles, Trash2, X } from 'lucide-react';
import type { Role, SkillSource } from './lib/profile-api';
import { installSkill, uninstallSkill } from './lib/profile-api';
import './skills-page.css';

type Gateway = { status: 'loading' | 'bridge_offline' | 'not_configured' | 'unknown' | 'offline' | 'online' };
type SkillMessage = { direction: 'operator' | 'assistant'; text: string };

function responseText(value: unknown, depth = 0): string | null {
  if (depth > 4 || value === null || value === undefined) return null;
  if (typeof value === 'string') return value.trim() || null;
  if (Array.isArray(value)) { const parts = value.map(item => responseText(item, depth + 1)).filter(Boolean) as string[]; return parts.length ? parts.join('\n') : null; }
  if (typeof value !== 'object') return null;
  const record = value as Record<string, unknown>;
  for (const key of ['output', 'response', 'answer', 'reply', 'message', 'content', 'text', 'final']) { const result = responseText(record[key], depth + 1); if (result) return result; }
  return null;
}

function normalizeRepository(value: string) {
  const raw = value.trim().replace(/\.+$/, '');
  const url = new URL(raw);
  if (url.protocol !== 'https:' || url.hostname !== 'github.com') throw new Error('Enter a public GitHub repository URL.');
  const parts = url.pathname.split('/').filter(Boolean);
  if (parts.length !== 2) throw new Error('Use a repository URL in the form github.com/owner/repository.');
  return `https://github.com/${parts[0]}/${parts[1].replace(/\.git$/, '')}`;
}

export function SkillsPage({ profileId, profileName, skills: initialSkills, roles, agentSkills, gateway, createSkill, run }: {
  profileId: string; profileName: string; skills: SkillSource[]; roles: Role[]; agentSkills: Record<string, string[]>; gateway: Gateway;
  createSkill: (name: string, repository: string, description: string) => Promise<SkillSource>; run: (input: string, session: string) => Promise<unknown>;
}) {
  const [skills, setSkills] = useState(initialSkills);
  const [importOpen, setImportOpen] = useState(false), [repository, setRepository] = useState(''), [importError, setImportError] = useState('');
  const [builderStarted, setBuilderStarted] = useState(false), [draft, setDraft] = useState(''), [messages, setMessages] = useState<SkillMessage[]>([]), [busy, setBusy] = useState(false), [builderError, setBuilderError] = useState('');
  const [installingId, setInstallingId] = useState('');
  const attachedCount = useMemo(() => roles.filter(role => (agentSkills[role.id] || []).length > 0).length, [agentSkills, roles]);

  const importSkillFn = async (event: FormEvent) => { event.preventDefault(); setImportError(''); try { const url = normalizeRepository(repository); if (skills.some(skill => skill.repository === url)) throw new Error('That repository is already registered in this profile.'); const name = url.split('/').at(-1) || 'GitHub skill'; const created = await createSkill(name, url, 'GitHub skill source. Review its code and configure any required credentials before use.'); setSkills(current => [...current, created]); setRepository(''); setImportOpen(false); } catch (error) { setImportError(error instanceof Error ? error.message : 'That repository could not be added.'); } };
  const askBuilder = async (event: FormEvent) => { event.preventDefault(); const request = draft.trim(); if (!request || busy) return; setBuilderStarted(true); setBuilderError(''); setMessages(current => [...current, { direction: 'operator', text: request }]); setDraft(''); if (gateway.status !== 'online') { setBuilderError('Connect the Hermes runtime before asking the skill engineer to design a skill.'); return; } setBusy(true); try { const result = await run(`You are the OrbityLabs skill engineer for the isolated profile "${profileName}". Design a skill specification for this request: ${request}\n\nReturn: a clear name, purpose, operator inputs, expected outputs, required configured providers/tools, security boundaries, and a verification plan. Do not claim the skill is installed, executable, connected, or approved. Do not expose or request secrets in chat. Use the profile only; do not access other profiles.`, `profile-${profileId}-skills-engineer`); const answer = responseText(result); if (!answer) throw new Error('The runtime accepted the request but did not return a skill specification.'); setMessages(current => [...current, { direction: 'assistant', text: answer }]); } catch (error) { setBuilderError(error instanceof Error ? error.message : 'The skill engineer could not complete that request.'); } finally { setBusy(false); } };

  const handleInstall = async (skill: SkillSource) => {
    setInstallingId(skill.id);
    try {
      const updated = await installSkill(profileId, skill.id);
      setSkills(current => current.map(s => s.id === skill.id ? { ...s, ...updated } : s));
    } catch { /* leave unchanged */ } finally { setInstallingId(''); }
  };
  const handleUninstall = async (skill: SkillSource) => {
    setInstallingId(skill.id);
    try {
      await uninstallSkill(profileId, skill.id);
      setSkills(current => current.map(s => s.id === skill.id ? { ...s, installed: false, installed_at: null, status: 'source' as const } : s));
    } catch { /* leave unchanged */ } finally { setInstallingId(''); }
  };

  const defaults = skills.filter(skill => skill.default), additions = skills.filter(skill => !skill.default);
  return <div className="page skills-page"><header className="skills-header"><div><h1>Skills</h1><p>Profile-scoped sources and skill design for {profileName}. Sources are not run until their code, credentials, and permissions are configured.</p></div><div className="skills-header-stats"><span><Bot size={14} />{attachedCount}/{roles.length} agents covered</span><span><Check size={14} />{skills.filter(s => s.installed).length} installed</span><span><ShieldCheck size={14} />{skills.length} sources</span></div></header><section className="skills-defaults" aria-labelledby="required-skills-title"><div className="skills-section-heading"><div><h2 id="required-skills-title">Default agent sources</h2><p>Every new agent in this profile starts with these source references. They are intentionally visible as sources—not installed credentials or permissions.</p></div><span className="skills-source-state"><Check size={14} /> Required baseline</span></div><div className="skills-source-list">{defaults.map(skill => <SkillSourceRow key={skill.id} skill={skill} busy={installingId === skill.id} onInstall={handleInstall} onUninstall={handleUninstall} />)}</div></section>{!builderStarted && <section className="skills-import-zone" aria-labelledby="import-skills-title"><div><GitBranch size={20} /><h2 id="import-skills-title">Add a GitHub skill</h2><p>Register a repository as a source for this profile. OrbityLabs will not download, execute, or grant it access automatically.</p></div><button className="skills-upload-button" onClick={() => { setImportOpen(true); setImportError(''); }}><Link size={17} /> Upload GitHub repository</button>{importOpen && <form className="skills-import-form" onSubmit={importSkillFn}><label>Repository URL<input autoFocus value={repository} onChange={event => setRepository(event.target.value)} placeholder="https://github.com/owner/repository" /></label><div><button className="button button-primary" type="submit">Add source</button><button className="button button-quiet" type="button" onClick={() => setImportOpen(false)}><X size={14} /> Cancel</button></div>{importError && <p className="form-error" role="alert">{importError}</p>}</form>}</section>}<section className={`skills-builder ${builderStarted ? 'started' : ''}`} aria-labelledby="skill-builder-title"><header><div><Sparkles size={18} /><div><h2 id="skill-builder-title">Skill engineer</h2><p>{builderStarted ? 'Continue the design conversation with the configured runtime.' : 'Describe a capability and the configured runtime will return a reviewable skill specification.'}</p></div></div>{gateway.status !== 'online' && <span className="skills-runtime-offline">Runtime offline</span>}</header>{builderStarted && <div className="skills-chat-log" aria-live="polite">{messages.map((message, index) => <article className={`skills-chat-message ${message.direction}`} key={index}><span>{message.direction === 'operator' ? 'You' : 'Skill engineer'}</span><p>{message.text}</p></article>)}{busy && <article className="skills-chat-message assistant"><span>Skill engineer</span><p>Preparing a specification…</p></article>}</div>}{builderError && <p className="form-error skills-builder-error" role="alert">{builderError}</p>}<form className="skills-builder-form" onSubmit={askBuilder}><textarea value={draft} onChange={event => setDraft(event.target.value)} placeholder={builderStarted ? 'Refine the skill or ask for implementation details…' : 'What skill should this profile be able to use?'} rows={builderStarted ? 3 : 4} /><button className="button button-primary" type="submit" disabled={busy || !draft.trim()}>{busy ? 'Working…' : builderStarted ? 'Send' : 'Design skill'} <Send size={14} /></button></form></section>{additions.length > 0 && <section className="skills-added-sources" aria-labelledby="profile-sources-title"><div className="skills-section-heading"><div><h2 id="profile-sources-title">Profile sources</h2><p>Repositories registered for this profile. Add configuration only after independently reviewing their code and requirements.</p></div></div><div className="skills-source-list">{additions.map(skill => <SkillSourceRow key={skill.id} skill={skill} busy={installingId === skill.id} onInstall={handleInstall} onUninstall={handleUninstall} />)}</div></section>}</div>;
}

function SkillSourceRow({ skill, busy, onInstall, onUninstall }: { skill: SkillSource; busy: boolean; onInstall: (s: SkillSource) => void; onUninstall: (s: SkillSource) => void }) {
  return <article className="skills-source-row">
    <div className="skills-source-icon"><GitBranch size={18} /></div>
    <div className="skills-source-copy">
      <strong>{skill.name}</strong>
      <p>{skill.description}</p>
      <a href={skill.repository} target="_blank" rel="noreferrer">{skill.repository.replace('https://github.com/', '')}<ArrowUpRight size={13} /></a>
      {skill.installed && skill.version && <small className="skill-version">v{skill.version}{skill.sha ? ` · ${skill.sha.slice(0, 7)}` : ''}</small>}
    </div>
    <div className="skills-source-actions">
      <span className={`skills-source-state ${skill.installed ? 'installed' : ''}`}>{skill.installed ? <><Check size={13} /> Installed</> : 'Source only'}</span>
      {skill.installed
        ? <button className="button button-quiet skill-action-btn" onClick={() => onUninstall(skill)} disabled={busy} title="Mark as not installed"><Trash2 size={13} /></button>
        : <button className="button button-quiet skill-action-btn" onClick={() => onInstall(skill)} disabled={busy} title="Mark as installed"><Download size={13} /></button>
      }
    </div>
  </article>;
}
