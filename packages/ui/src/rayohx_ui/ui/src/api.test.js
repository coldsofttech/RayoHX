import { afterEach, describe, expect, it, vi } from 'vitest';

import * as api from './api';

/**
 * @param {number} status
 * @param {unknown} [body]
 */
const reply = (status, body) =>
  vi.fn().mockResolvedValue({ status, ok: status < 400, json: () => Promise.resolve(body) });

describe('api', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('posts JSON to the v1 routes', async () => {
    const fetch = reply(200, { playlist: {} });
    vi.stubGlobal('fetch', fetch);
    await api.inspect('https://x/m.m3u8', { Referer: 'r' });
    const [path, init] = fetch.mock.calls[0];
    expect(path).toBe('/api/v1/inspect');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({
      url: 'https://x/m.m3u8',
      network: { headers: { Referer: 'r' } },
    });
  });

  it('sends no body on a plain GET', async () => {
    const fetch = reply(200, { items: [] });
    vi.stubGlobal('fetch', fetch);
    await api.listDownloads();
    expect(fetch.mock.calls[0][1].body).toBeUndefined();
  });

  it('returns null for 204', async () => {
    vi.stubGlobal('fetch', reply(204));
    expect(await api.removeDownload('a')).toBeNull();
  });

  it('raises the problem detail', async () => {
    vi.stubGlobal('fetch', reply(422, { detail: 'Not a playlist.' }));
    await expect(api.inspect('x')).rejects.toThrow('Not a playlist.');
  });

  it('falls back when the error has no usable detail', async () => {
    vi.stubGlobal('fetch', reply(422, { detail: [{ msg: 'bad' }] }));
    await expect(api.saveSettings({})).rejects.toThrow('The request was not valid.');
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue({ status: 500, ok: false, json: () => Promise.reject(new Error('x')) }),
    );
    await expect(api.getSettings()).rejects.toThrow('Request failed (500)');
  });
});
