// Every download option the API accepts, described once. The form is drawn from this list and the
// request is built from it, so adding an option is one line here.
//
// type: text | number | bool | select | list (comma separated) | lines (one per line) | secret
// scale: multiplies a number into the API's unit (for example MB to bytes).
// noDefault: never saved as a default (logins and passwords).
// defaultsOnly: only in the defaults editor; the new-download form has its own control.
// local: refers to a file on this machine; only shown when the API allows it.

export const QUALITIES = ['best', '1080p', '720p', '480p', '360p', 'worst', 'auto'];

const yes = (label, key, hint) => ({ key, label, type: 'bool', hint });

export const SECTIONS = [
  {
    id: 'selection',
    title: 'Stream selection',
    fields: [
      {
        key: 'quality',
        label: 'Quality',
        type: 'select',
        options: QUALITIES,
        defaultsOnly: true,
      },
      {
        key: 'variant',
        label: 'Stream number',
        type: 'number',
        hint: 'Pick a stream by its number. Cannot be combined with the other stream filters.',
      },
      { key: 'resolution', label: 'Exact size', type: 'text', hint: 'For example 1280x720.' },
      { key: 'max_resolution', label: 'Highest height', type: 'text', hint: 'For example 1080p.' },
      { key: 'bandwidth', label: 'Exact bitrate (kbps)', type: 'number', scale: 1000 },
      { key: 'max_bitrate', label: 'Highest bitrate (kbps)', type: 'number', scale: 1000 },
      { key: 'variant_name', label: 'Stream name', type: 'text' },
      {
        key: 'codec',
        label: 'Preferred codec',
        type: 'select',
        options: ['h264', 'hevc', 'vp9', 'av1'],
      },
      {
        key: 'video_range',
        label: 'Preferred range',
        type: 'select',
        options: ['sdr', 'pq', 'hlg', 'hdr'],
      },
      { key: 'max_frame_rate', label: 'Highest frame rate', type: 'number' },
      { key: 'audio_names', label: 'Audio track names', type: 'list' },
      { key: 'subtitle_names', label: 'Subtitle track names', type: 'list' },
      yes('Video only (no separate audio or subtitles)', 'video_only'),
    ],
  },
  {
    id: 'network',
    title: 'Network',
    fields: [
      {
        key: 'headers',
        label: 'Headers',
        type: 'lines',
        hint: 'One per line, as Name: value.',
        pairs: ':',
      },
      {
        key: 'cookies',
        label: 'Cookies',
        type: 'lines',
        hint: 'One per line, as name=value.',
        pairs: '=',
      },
      { key: 'cookie_file', label: 'Cookie file (cookies.txt)', type: 'text', local: true },
      { key: 'user_agent', label: 'User agent', type: 'text' },
      { key: 'referer', label: 'Referer', type: 'text' },
      { key: 'origin', label: 'Origin', type: 'text' },
      {
        key: 'proxy.url',
        label: 'Proxy',
        type: 'text',
        hint: 'http://, https://, socks5:// or socks5h://',
      },
      { key: 'proxy.username', noDefault: true, label: 'Proxy user', type: 'text' },
      { key: 'proxy.password', noDefault: true, label: 'Proxy password', type: 'secret' },
      yes('Use proxy settings from the environment', 'env_proxy'),
      { key: 'retries', label: 'Retries', type: 'number' },
      { key: 'backoff', label: 'Back-off factor', type: 'number' },
      { key: 'max_redirects', label: 'Most redirects', type: 'number' },
      { key: 'connect_timeout', label: 'Connect timeout (s)', type: 'number' },
      { key: 'read_timeout', label: 'Read timeout (s)', type: 'number' },
      { key: 'timeout', label: 'Total time allowed (s)', type: 'number' },
      { key: 'rate_limit', label: 'Speed limit (KB/s)', type: 'number', scale: 1024 },
      { key: 'credential_hosts', label: 'Hosts that may get credentials', type: 'list' },
      yes('Do not verify TLS certificates (unsafe)', 'insecure'),
      { key: 'ca_bundle', label: 'CA bundle', type: 'text', local: true },
      { key: 'client_cert', label: 'Client certificate', type: 'text', local: true },
      { key: 'client_key', label: 'Client key', type: 'text', local: true },
      { key: 'client_key_password', noDefault: true, label: 'Client key password', type: 'secret' },
    ],
  },
  {
    id: 'output',
    title: 'Output',
    fields: [
      {
        key: 'format',
        label: 'Format',
        type: 'select',
        options: ['auto', 'mp4', 'ts', 'segments'],
      },
      { key: 'directory', label: 'Folder (inside the download folder)', type: 'text' },
      {
        key: 'remux_backend',
        label: 'Remux with',
        type: 'select',
        options: ['auto', 'native', 'ffmpeg'],
      },
      { key: 'ffmpeg', label: 'FFmpeg path', type: 'text', local: true },
      yes('Replace files that already exist', 'overwrite'),
      { key: 'validate', label: 'Check the finished file', type: 'bool', fallback: true },
    ],
  },
  {
    id: 'storage',
    title: 'Storage',
    fields: [
      {
        key: 'strategy',
        label: 'Strategy',
        type: 'select',
        options: ['auto', 'direct', 'streaming', 'buffered', 'temporary', 'hybrid'],
      },
      { key: 'workspace', label: 'Working folder (inside the download folder)', type: 'text' },
      { key: 'buffer_bytes', label: 'Memory buffer (MB)', type: 'number', scale: 1048576 },
      { key: 'max_temp_bytes', label: 'Most temporary data (MB)', type: 'number', scale: 1048576 },
      { key: 'reserve_bytes', label: 'Free space to keep (MB)', type: 'number', scale: 1048576 },
      { key: 'space_check', label: 'Check free space', type: 'bool', fallback: true },
      {
        key: 'keep_state',
        label: 'Keep resume state after a failure',
        type: 'bool',
        fallback: true,
      },
    ],
  },
  {
    id: 'engine',
    title: 'Engine',
    fields: [
      { key: 'concurrency', label: 'Parallel segments', type: 'number' },
      { key: 'resume', label: 'Resume partial downloads', type: 'bool', fallback: true },
      {
        key: 'allow_file_keys',
        label: 'Allow file: key addresses',
        type: 'bool',
        local: true,
        hint: 'Lets a stream make RayoHX read key files from this machine.',
      },
    ],
  },
];

function setPath(target, path, value) {
  const parts = path.split('.');
  let node = target;
  for (const part of parts.slice(0, -1)) {
    node[part] ??= {};
    node = node[part];
  }
  node[parts.at(-1)] = value;
}

function parsePairs(text, separator) {
  const result = {};
  for (const line of text.split('\n')) {
    const at = line.indexOf(separator);
    if (at > 0) result[line.slice(0, at).trim()] = line.slice(at + 1).trim();
  }
  return result;
}

/** The value of one field as the API wants it, or undefined if the user left it alone. */
export function convert(field, raw) {
  if (raw === undefined || raw === '') return undefined;
  switch (field.type) {
    case 'number': {
      const number = Number(raw);
      return Number.isFinite(number)
        ? Math.round(number * (field.scale ?? 1) * 1000) / 1000
        : undefined;
    }
    case 'list': {
      const items = raw
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean);
      return items.length ? items : undefined;
    }
    case 'lines': {
      const pairs = parsePairs(raw, field.pairs);
      return Object.keys(pairs).length ? pairs : undefined;
    }
    case 'bool':
      return Boolean(raw);
    default:
      return raw;
  }
}

/** Builds the section objects of a download request from what the form holds. */
export function buildOptions(values) {
  const request = {};
  for (const section of SECTIONS) {
    const body = {};
    for (const field of section.fields) {
      const value = convert(field, values[`${section.id}.${field.key}`]);
      if (value !== undefined) setPath(body, field.key, value);
    }
    if (Object.keys(body).length) request[section.id] = body;
  }
  return request;
}

/** Builds the source part: one address, several, or playlist text with its base address. */
export function buildSource(mode, input) {
  if (mode === 'many') {
    const urls = input.urls
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith('#'));
    return { urls };
  }
  if (mode === 'text') return { playlist_text: input.text, base_url: input.base.trim() };
  return { url: input.url.trim() };
}

const text = (value) => (value === undefined || value === null ? undefined : String(value));

function getPath(source, path) {
  return path.split('.').reduce((node, part) => (node == null ? undefined : node[part]), source);
}

/** The reverse of buildOptions: turns saved defaults into the form's flat values. */
export function toValues(nested = {}) {
  const values = {};
  for (const section of SECTIONS) {
    for (const field of section.fields) {
      const raw = getPath(nested[section.id], field.key);
      if (raw === undefined || raw === null) continue;
      const id = `${section.id}.${field.key}`;
      if (field.type === 'bool') values[id] = Boolean(raw);
      else if (field.type === 'list') values[id] = raw.join(', ');
      else if (field.type === 'lines')
        values[id] = Object.entries(raw)
          .map(([name, value]) => `${name}${field.pairs} ${value}`)
          .join('\n');
      else if (field.type === 'number') values[id] = text(raw / (field.scale ?? 1));
      else values[id] = text(raw);
    }
  }
  return values;
}
