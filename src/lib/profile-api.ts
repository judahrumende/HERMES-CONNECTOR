import { useCallback, useEffect, useState } from 'react';

export type Status = 'live' | 'idle' | 'blocked' | 'draft';
export type WorkspaceProfile = { id: string; name: string; kind: string; context: string; vault_path: string; created_at: string };
export type Role = { id: string; name: string; role: string; initials: string };
export type Task = { id: string; title: string; area: string; state: Status };
export type Source = { id: string; title: string; detail: string };
export type ApprovalMode = 'manual' | 'auto_safe';
export type AgentRuntime = { provider: string; model: string };
export type SkillSource = { id: string; name: string; repository: string; description: string; default: boolean; status: 'source' | 'installed'; installed: boolean; installed_at: string | null; version: string; sha: string; created_at: string };
export type GlobalProfileContext = {
  profile_id: string;
  name: string;
  kind: string;
  context: string;
  vault_path: string;
  agents: Array<{ name: string; role: string }>;
  sources: string[];
};
export type Message = { id: string; profile_id: string; agent_id: string; direction: 'outgoing' | 'incoming'; text: string; run_id: string; at: string };
export type MessagePreview = { agent_id: string; text: string; direction: string; at: string };
export type Approval = { id: string; profile_id: string; agent_id: string; session_id: string; kind: string; summary: string; payload: Record<string, unknown>; state: 'pending' | 'approved' | 'denied'; decided_at: string | null; run_id: string; created_at: string };
export type ToolEvent = { id: number; profile_id: string; run_id: string; agent_id: string; tool_name: string; input: Record<string, unknown>; output: Record<string, unknown>; status: string; duration_ms: number; at: string };
export type DoctorCheck = { name: string; status: 'ok' | 'warning' | 'error'; detail: string };
export type DoctorReport = { checks: DoctorCheck[]; gateway: Record<string, unknown>; config_file: string; db_stats: Record<string, number> };
export type RuntimeConfig = { provider: string; model: string; api_key_set: boolean; base_url: string; mode: string; ready: boolean };
export type AgentMemory = { key: string; content: string; updated_at: string };
export type SkillDoc = { name: string; description: string; agent_id: string; updated_at: string };

async function apiRequest<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...options });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
  return body as T;
}

export function fetchGlobalContext(): Promise<GlobalProfileContext[]> {
  return apiRequest<GlobalProfileContext[]>('/api/global/context');
}

export function useProfiles() {
  const [profiles, setProfiles] = useState<WorkspaceProfile[]>([]);
  useEffect(() => {
    let active = true;
    apiRequest<WorkspaceProfile[]>('/api/profiles').then(list => { if (active) setProfiles(list); }).catch(() => undefined);
    return () => { active = false; };
  }, []);
  const createProfile = async (name: string, kind: string, context: string, vaultPath: string) => {
    const created = await apiRequest<WorkspaceProfile>('/api/profiles', {
      method: 'POST',
      body: JSON.stringify({ name, kind, context, vault_path: vaultPath }),
    });
    setProfiles(current => [...current, created]);
    return created;
  };
  return { profiles, createProfile };
}

export function useProfileAgents(profileId: string) {
  const [agents, setAgents] = useState<Role[]>([]);
  useEffect(() => {
    if (!profileId) { setAgents([]); return; }
    let active = true;
    apiRequest<Role[]>(`/api/profiles/${profileId}/agents`).then(list => { if (active) setAgents(list); }).catch(() => { if (active) setAgents([]); });
    return () => { active = false; };
  }, [profileId]);
  const createAgent = async (name: string, role: string, initials: string) => {
    const created = await apiRequest<Role>(`/api/profiles/${profileId}/agents`, {
      method: 'POST',
      body: JSON.stringify({ name, role, initials }),
    });
    setAgents(current => [...current, created]);
    return created;
  };
  return { agents, createAgent };
}

export function useProfileSkills(profileId: string) {
  const [skills, setSkills] = useState<SkillSource[]>([]);
  const [agentSkills, setAgentSkills] = useState<Record<string, string[]>>({});
  useEffect(() => {
    if (!profileId) { setSkills([]); setAgentSkills({}); return; }
    let active = true;
    Promise.all([
      apiRequest<SkillSource[]>(`/api/profiles/${profileId}/skills`),
      apiRequest<Record<string, string[]>>(`/api/profiles/${profileId}/agent-skills`),
    ]).then(([nextSkills, nextAgentSkills]) => { if (active) { setSkills(nextSkills); setAgentSkills(nextAgentSkills); } }).catch(() => { if (active) { setSkills([]); setAgentSkills({}); } });
    return () => { active = false; };
  }, [profileId]);
  const createSkill = async (name: string, repository: string, description: string) => {
    const created = await apiRequest<SkillSource>(`/api/profiles/${profileId}/skills`, {
      method: 'POST', body: JSON.stringify({ name, repository, description }),
    });
    setSkills(current => [...current, created]);
    return created;
  };
  return { skills, agentSkills, createSkill };
}

export function useProfileTasks(profileId: string) {
  const [tasks, setTasks] = useState<Task[]>([]);
  useEffect(() => {
    if (!profileId) { setTasks([]); return; }
    let active = true;
    apiRequest<Task[]>(`/api/profiles/${profileId}/tasks`).then(list => { if (active) setTasks(list); }).catch(() => { if (active) setTasks([]); });
    return () => { active = false; };
  }, [profileId]);
  const createTask = async (title: string, area: string, state: Status) => {
    const created = await apiRequest<Task>(`/api/profiles/${profileId}/tasks`, {
      method: 'POST',
      body: JSON.stringify({ title, area, state }),
    });
    setTasks(current => [...current, created]);
  };
  const toggleTask = (id: string) => {
    const target = tasks.find(task => task.id === id);
    if (!target) return;
    const nextState: Status = target.state === 'live' ? 'draft' : 'live';
    setTasks(current => current.map(task => (task.id === id ? { ...task, state: nextState } : task)));
    apiRequest(`/api/profiles/${profileId}/tasks/${id}`, { method: 'PATCH', body: JSON.stringify({ state: nextState }) })
      .catch(() => setTasks(current => current.map(task => (task.id === id ? { ...task, state: target.state } : task))));
  };
  const deleteTask = (id: string) => {
    setTasks(current => current.filter(task => task.id !== id));
    apiRequest(`/api/profiles/${profileId}/tasks/${id}`, { method: 'DELETE' }).catch(() => undefined);
  };
  return { tasks, createTask, toggleTask, deleteTask };
}

export function useProfileSources(profileId: string) {
  const [sources, setSources] = useState<Source[]>([]);
  useEffect(() => {
    if (!profileId) { setSources([]); return; }
    let active = true;
    apiRequest<Source[]>(`/api/profiles/${profileId}/sources`).then(list => { if (active) setSources(list); }).catch(() => { if (active) setSources([]); });
    return () => { active = false; };
  }, [profileId]);
  const createSource = async (title: string, detail: string) => {
    const created = await apiRequest<Source>(`/api/profiles/${profileId}/sources`, {
      method: 'POST',
      body: JSON.stringify({ title, detail }),
    });
    setSources(current => [...current, created]);
  };
  return { sources, createSource };
}

export function useProfilePolicy(profileId: string) {
  const [autonomy, setAutonomyState] = useState<ApprovalMode>('manual');
  useEffect(() => {
    if (!profileId) { setAutonomyState('manual'); return; }
    let active = true;
    apiRequest<{ autonomy: string }>(`/api/profiles/${profileId}/policy`)
      .then(value => { if (active) setAutonomyState(value.autonomy === 'auto_safe' ? 'auto_safe' : 'manual'); })
      .catch(() => undefined);
    return () => { active = false; };
  }, [profileId]);
  const setAutonomy = (mode: ApprovalMode) => {
    setAutonomyState(mode);
    apiRequest(`/api/profiles/${profileId}/policy`, { method: 'PUT', body: JSON.stringify({ autonomy: mode }) }).catch(() => undefined);
  };
  return { autonomy, setAutonomy };
}

export function useProfileModelRoutes(profileId: string) {
  const [routes, setRoutes] = useState<Record<string, AgentRuntime>>({});
  useEffect(() => {
    if (!profileId) { setRoutes({}); return; }
    let active = true;
    apiRequest<Record<string, AgentRuntime>>(`/api/profiles/${profileId}/model-routes`).then(map => {
      if (!active) return;
      const next: Record<string, AgentRuntime> = {};
      for (const [key, value] of Object.entries(map)) { if (key !== 'default') next[key] = value; }
      setRoutes(next);
    }).catch(() => { if (active) setRoutes({}); });
    return () => { active = false; };
  }, [profileId]);
  const setRoute = (agentId: string, provider: string, model: string) => {
    setRoutes(current => ({ ...current, [agentId]: { provider, model } }));
    apiRequest(`/api/profiles/${profileId}/model-routes`, {
      method: 'PUT',
      body: JSON.stringify({ agent_id: agentId, provider, model }),
    }).catch(() => undefined);
  };
  return { routes, setRoute };
}

export function useProfileMessages(profileId: string, agentId: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const isReal = Boolean(profileId && profileId !== 'unassigned' && agentId);
  useEffect(() => {
    if (!isReal) { setMessages([]); return; }
    let active = true;
    apiRequest<Message[]>(`/api/profiles/${profileId}/messages?agent_id=${encodeURIComponent(agentId)}&limit=200`)
      .then(list => { if (active) setMessages(list); })
      .catch(() => { if (active) setMessages([]); });
    return () => { active = false; };
  }, [profileId, agentId, isReal]);

  const saveMessage = useCallback(async (direction: 'outgoing' | 'incoming', text: string, runId = '') => {
    if (!isReal) return null;
    try {
      const msg = await apiRequest<Message>(`/api/profiles/${profileId}/messages`, {
        method: 'POST',
        body: JSON.stringify({ agent_id: agentId, direction, text, run_id: runId }),
      });
      setMessages(current => [...current, msg]);
      return msg;
    } catch { return null; }
  }, [profileId, agentId, isReal]);

  return { messages, setMessages, saveMessage };
}

export function useMessagePreviews(profileId: string) {
  const [previews, setPreviews] = useState<MessagePreview[]>([]);
  useEffect(() => {
    if (!profileId || profileId === 'unassigned') { setPreviews([]); return; }
    let active = true;
    apiRequest<MessagePreview[]>(`/api/profiles/${profileId}/message-previews`)
      .then(list => { if (active) setPreviews(list); })
      .catch(() => { if (active) setPreviews([]); });
    return () => { active = false; };
  }, [profileId]);
  return previews;
}

export function searchMessages(profileId: string, query: string): Promise<Message[]> {
  if (!profileId || profileId === 'unassigned' || !query.trim()) return Promise.resolve([]);
  return apiRequest<Message[]>(`/api/profiles/${profileId}/messages/search?q=${encodeURIComponent(query)}`);
}

export function useProfileApprovals(profileId: string) {
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const isReal = Boolean(profileId && profileId !== 'unassigned');
  const load = useCallback(() => {
    if (!isReal) { setApprovals([]); return; }
    apiRequest<Approval[]>(`/api/profiles/${profileId}/approvals`)
      .then(list => setApprovals(list))
      .catch(() => setApprovals([]));
  }, [profileId, isReal]);
  useEffect(() => { load(); }, [load]);

  const createApproval = async (agentId: string, sessionId: string, kind: string, summary: string, payload: Record<string, unknown>) => {
    const item = await apiRequest<Approval>(`/api/profiles/${profileId}/approvals`, {
      method: 'POST',
      body: JSON.stringify({ agent_id: agentId, session_id: sessionId, kind, summary, payload }),
    });
    setApprovals(current => [item, ...current]);
    return item;
  };

  const decideApproval = async (approvalId: string, state: 'approved' | 'denied') => {
    const item = await apiRequest<Approval>(`/api/profiles/${profileId}/approvals/${approvalId}`, {
      method: 'PATCH',
      body: JSON.stringify({ state }),
    });
    setApprovals(current => current.map(a => a.id === approvalId ? item : a));
    return item;
  };

  return { approvals, load, createApproval, decideApproval };
}

export function useProfileToolEvents(profileId: string, runId = '') {
  const [toolEvents, setToolEvents] = useState<ToolEvent[]>([]);
  const isReal = Boolean(profileId && profileId !== 'unassigned');
  useEffect(() => {
    if (!isReal) { setToolEvents([]); return; }
    let active = true;
    const url = `/api/profiles/${profileId}/tool-events?limit=50${runId ? `&run_id=${encodeURIComponent(runId)}` : ''}`;
    apiRequest<ToolEvent[]>(url).then(list => { if (active) setToolEvents(list); }).catch(() => { if (active) setToolEvents([]); });
    return () => { active = false; };
  }, [profileId, runId, isReal]);

  const recordToolEvent = (run_id: string, agent_id: string, tool_name: string, input: Record<string, unknown>, output: Record<string, unknown>, status = 'ok', duration_ms = 0) => {
    if (!isReal) return;
    apiRequest(`/api/profiles/${profileId}/tool-events`, {
      method: 'POST',
      body: JSON.stringify({ run_id, agent_id, tool_name, input, output, status, duration_ms }),
    }).catch(() => undefined);
  };

  return { toolEvents, recordToolEvent };
}

export function useDoctorReport() {
  const [report, setReport] = useState<DoctorReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const load = useCallback(() => {
    setLoading(true); setError('');
    apiRequest<DoctorReport>('/api/doctor')
      .then(r => setReport(r))
      .catch(e => setError(e instanceof Error ? e.message : 'Could not load doctor report.'))
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);
  return { report, loading, error, load };
}

export function installSkill(profileId: string, skillId: string, version = '', sha = ''): Promise<SkillSource> {
  return apiRequest<SkillSource>(`/api/profiles/${profileId}/skills/${skillId}/install`, {
    method: 'POST',
    body: JSON.stringify({ version, sha }),
  });
}

export function uninstallSkill(profileId: string, skillId: string): Promise<void> {
  return apiRequest<void>(`/api/profiles/${profileId}/skills/${skillId}/uninstall`, { method: 'POST' });
}

export function stopRun(runId: string): Promise<Record<string, unknown>> {
  return apiRequest<Record<string, unknown>>(`/api/hermes/runs/${runId}`, { method: 'DELETE' });
}

// -- new types ------------------------------------------------------------------
export type Run = { id: string; profile_id: string; agent_id: string; session_id: string; status: string; input_preview: string; started_at: string; ended_at: string | null; tool_count: number };
export type ScheduledDirective = { id: string; profile_id: string; agent_id: string; directive: string; interval_seconds: number; enabled: boolean; last_run_at: string | null; last_run_id: string | null; last_error: string | null; created_at: string };
export type VaultFile = { path: string; modified_at: string; size: number };
export type GroupRunResult = { runs: Array<{ agent_id: string; run_id?: string; error?: string; status: string }> };

// -- run timeline ---------------------------------------------------------------
export function useProfileRuns(profileId: string) {
  const [runs, setRuns] = useState<Run[]>([]);
  const isReal = Boolean(profileId && profileId !== 'unassigned');
  const load = useCallback(() => {
    if (!isReal) { setRuns([]); return; }
    apiRequest<Run[]>(`/api/profiles/${profileId}/runs?limit=100`).then(setRuns).catch(() => setRuns([]));
  }, [profileId, isReal]);
  useEffect(() => { load(); }, [load]);
  return { runs, load };
}

// -- scheduled directives -------------------------------------------------------
export function useScheduledDirectives(profileId: string) {
  const [directives, setDirectives] = useState<ScheduledDirective[]>([]);
  const isReal = Boolean(profileId && profileId !== 'unassigned');
  const load = useCallback(() => {
    if (!isReal) { setDirectives([]); return; }
    apiRequest<ScheduledDirective[]>(`/api/profiles/${profileId}/scheduled-directives`).then(setDirectives).catch(() => setDirectives([]));
  }, [profileId, isReal]);
  useEffect(() => { load(); }, [load]);

  const createDirective = async (agentId: string, directive: string, intervalSeconds: number) => {
    const item = await apiRequest<ScheduledDirective>(`/api/profiles/${profileId}/scheduled-directives`, {
      method: 'POST', body: JSON.stringify({ agent_id: agentId, directive, interval_seconds: intervalSeconds }),
    });
    setDirectives(d => [item, ...d]);
    return item;
  };

  const updateDirective = async (id: string, updates: Partial<Pick<ScheduledDirective, 'directive' | 'agent_id' | 'interval_seconds' | 'enabled'>>) => {
    const item = await apiRequest<ScheduledDirective>(`/api/profiles/${profileId}/scheduled-directives/${id}`, {
      method: 'PATCH', body: JSON.stringify(updates),
    });
    setDirectives(d => d.map(x => x.id === id ? item : x));
    return item;
  };

  const deleteDirective = async (id: string) => {
    await apiRequest<void>(`/api/profiles/${profileId}/scheduled-directives/${id}`, { method: 'DELETE' });
    setDirectives(d => d.filter(x => x.id !== id));
  };

  return { directives, load, createDirective, updateDirective, deleteDirective };
}

// -- group run ------------------------------------------------------------------
export function createGroupRun(profileId: string, agentIds: string[], directive: string): Promise<GroupRunResult> {
  return apiRequest<GroupRunResult>(`/api/profiles/${profileId}/group-run`, {
    method: 'POST', body: JSON.stringify({ agent_ids: agentIds, directive }),
  });
}

// -- profile export / import ----------------------------------------------------
export async function exportProfile(profileId: string): Promise<void> {
  const resp = await fetch(`/api/profiles/${profileId}/export`);
  if (!resp.ok) throw new Error('Export failed');
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = `profile-${profileId.slice(0, 8)}.json`; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

export async function importProfile(file: File): Promise<{ id: string; name: string }> {
  const text = await file.text();
  const data = JSON.parse(text);
  return apiRequest<{ id: string; name: string }>('/api/profiles/import', {
    method: 'POST', body: JSON.stringify(data),
  });
}

// -- vault diff -----------------------------------------------------------------
export function useVaultDiff(profileId: string) {
  const [files, setFiles] = useState<VaultFile[]>([]);
  const [loading, setLoading] = useState(false);
  const [since, setSince] = useState<string | null>(null);
  const isReal = Boolean(profileId && profileId !== 'unassigned');
  const load = useCallback((sinceDate?: string | null) => {
    if (!isReal) return;
    setLoading(true);
    const url = `/api/profiles/${profileId}/vault-diff${sinceDate ? `?since=${encodeURIComponent(sinceDate)}` : ''}`;
    apiRequest<VaultFile[]>(url).then(list => { setFiles(list); setSince(new Date().toISOString()); }).catch(() => {}).finally(() => setLoading(false));
  }, [profileId, isReal]);
  useEffect(() => { load(); }, [load]);
  return { files, loading, since, reload: () => load(since) };
}

// -- approvals export -----------------------------------------------------------
export async function exportApprovals(profileId: string, fmt: 'json' | 'csv' = 'json'): Promise<void> {
  const resp = await fetch(`/api/profiles/${profileId}/approvals/export?fmt=${fmt}`);
  if (!resp.ok) throw new Error('Export failed');
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = `approvals.${fmt}`; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

// -- agent notes ----------------------------------------------------------------
export function useAgentNotes(profileId: string, agentId: string) {
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const isReal = Boolean(profileId && profileId !== 'unassigned' && agentId);
  useEffect(() => {
    if (!isReal) { setNotes(''); return; }
    apiRequest<{ notes: string }>(`/api/profiles/${profileId}/agents/${encodeURIComponent(agentId)}/notes`)
      .then(r => setNotes(r.notes))
      .catch(() => setNotes(''));
  }, [profileId, agentId, isReal]);
  const save = async (value: string) => {
    if (!isReal) return;
    setSaving(true);
    try {
      await apiRequest(`/api/profiles/${profileId}/agents/${encodeURIComponent(agentId)}/notes`, {
        method: 'PUT',
        body: JSON.stringify({ notes: value }),
      });
      setNotes(value);
    } finally {
      setSaving(false);
    }
  };
  return { notes, setNotes, save, saving };
}

// -- runtime config ------------------------------------------------------------
export function useRuntimeConfig() {
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const load = () => apiRequest<RuntimeConfig>('/api/runtime/config').then(setConfig).catch(() => {});
  useEffect(() => { load(); }, []);
  const save = async (provider: string, model: string, apiKey: string, baseUrl = '') => {
    setSaving(true);
    try {
      const result = await apiRequest<Record<string, unknown>>('/api/runtime/config', {
        method: 'PUT',
        body: JSON.stringify({ provider, model, api_key: apiKey, base_url: baseUrl }),
      });
      await load();
      return result;
    } finally { setSaving(false); }
  };
  return { config, save, saving, reload: load };
}

// -- agent memories ------------------------------------------------------------
export function useAgentMemories(profileId: string, agentId: string) {
  const [memories, setMemories] = useState<AgentMemory[]>([]);
  const isReal = Boolean(profileId && profileId !== 'unassigned' && agentId);
  const load = () => {
    if (!isReal) { setMemories([]); return; }
    apiRequest<AgentMemory[]>(`/api/profiles/${profileId}/agents/${encodeURIComponent(agentId)}/memories`)
      .then(setMemories).catch(() => setMemories([]));
  };
  useEffect(() => { load(); }, [profileId, agentId, isReal]);
  const upsert = async (key: string, content: string) => {
    await apiRequest(`/api/profiles/${profileId}/agents/${encodeURIComponent(agentId)}/memories`, {
      method: 'PUT', body: JSON.stringify({ key, content }),
    });
    load();
  };
  const remove = async (key: string) => {
    await apiRequest(`/api/profiles/${profileId}/agents/${encodeURIComponent(agentId)}/memories/${encodeURIComponent(key)}`, { method: 'DELETE' });
    load();
  };
  return { memories, upsert, remove, reload: load };
}

// -- skill docs (agent-created learning loop) ----------------------------------
export function useSkillDocs(profileId: string) {
  const [docs, setDocs] = useState<SkillDoc[]>([]);
  const isReal = Boolean(profileId && profileId !== 'unassigned');
  useEffect(() => {
    if (!isReal) { setDocs([]); return; }
    apiRequest<SkillDoc[]>(`/api/profiles/${profileId}/skill-docs`).then(setDocs).catch(() => setDocs([]));
  }, [profileId, isReal]);
  const remove = async (name: string) => {
    await apiRequest(`/api/profiles/${profileId}/skill-docs/${encodeURIComponent(name)}`, { method: 'DELETE' });
    setDocs(d => d.filter(x => x.name !== name));
  };
  return { docs, remove };
}

// -- webhook url helper ---------------------------------------------------------
export function webhookUrl(profileId: string): string {
  return `${window.location.origin}/api/webhooks/${profileId}`;
}
