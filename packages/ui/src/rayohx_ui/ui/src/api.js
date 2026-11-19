// The only place the page talks to Python: the rayohx_api routes under /api/v1 (the New and
// Settings pages) and /api/v2 (the queue, storage and diagnostics pages).
const BASE = '/api/v1';
const V2 = '/api/v2';

export class ApiError extends Error {}

async function call(path, { method = 'GET', body, base = BASE } = {}) {
  const response = await fetch(`${base}${path}`, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail ?? data.title ?? `Request failed (${response.status})`;
    throw new ApiError(typeof detail === 'string' ? detail : 'The request was not valid.');
  }
  return data;
}

export const inspect = (request) => call('/inspect', { method: 'POST', body: request });
export const listDownloads = () => call('/downloads');
export const startDownload = (request) => call('/downloads', { method: 'POST', body: request });
export const controlDownload = (id, action) =>
  call(`/downloads/${id}/${action}`, { method: 'POST' });
export const removeDownload = (id) => call(`/downloads/${id}`, { method: 'DELETE' });
export const getSettings = () => call('/settings');
export const saveDefaults = (defaults) =>
  call('/settings/defaults', { method: 'PUT', body: defaults });
export const downloadLog = (id) => call(`/downloads/${id}/log`);
export const clean = (request) => call('/clean', { method: 'POST', body: request });

// --- version 2: the persistent queue, storage and diagnostics ---
const v2 = (path, options = {}) => call(path, { ...options, base: V2 });

export const queueList = () => v2('/queue');
export const queueAction = (action, ids, extra = {}) =>
  v2('/queue/actions', { method: 'POST', body: { action, ids, ...extra } });
export const queueJob = (id) => v2(`/queue/${id}`);
export const queueVerification = (id) => v2(`/queue/${id}/verification`);
export const setMaxActive = (maxActive) =>
  v2('/queue/settings', { method: 'PUT', body: { max_active: maxActive } });
export const explainJob = (id) => v2(`/diagnostics/jobs/${id}`);
export const makeReport = (jobId) =>
  v2('/diagnostics/report', { method: 'POST', body: { job_id: jobId } });
export const jobEvents = (id) => v2(`/events?job_id=${encodeURIComponent(id)}&limit=100`);
export const storageStatus = () => v2('/storage');
export const storageWorkspaces = () => v2('/storage/workspaces');
export const setStoragePolicy = (policy) => v2('/storage/policy', { method: 'PUT', body: policy });
export const storageCleanup = (request) =>
  v2('/storage/cleanup', { method: 'POST', body: request });
