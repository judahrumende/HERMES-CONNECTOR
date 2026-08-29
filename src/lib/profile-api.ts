import { useEffect, useState } from 'react';

export type Status = 'live' | 'idle' | 'blocked' | 'draft';
export type WorkspaceProfile = { id: string; name: string; kind: string; context: string; vault_path: string; created_at: string };
export type Role = { id: string; name: string; role: string; initials: string };
export type Task = { id: string; title: string; area: string; state: Status };
export type Source = { id: string; title: string; detail: string };
export type ApprovalMode = 'manual' | 'auto_safe';
export type AgentRuntime = { provider: string; model: string };
export type SkillSource = { id: string; name: string; repository: string; description: string; default: boolean; status: 'source'; created_at: string };
export type GlobalProfileContext = {
  profile_id: string;
  name: string;
  kind: string;
  context: string;
  vault_path: string;
  agents: Array<{ name: string; role: string }>;
  sources: string[];
};

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
