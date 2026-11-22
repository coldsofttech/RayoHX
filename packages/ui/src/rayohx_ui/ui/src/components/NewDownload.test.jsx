import { StrictMode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { axe } from 'vitest-axe';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import NewDownload from './NewDownload.jsx';

const MASTER = {
  type: 'master',
  url: 'https://x/m.m3u8',
  variants: [
    { index: 1, name: null, resolution: '1280x720', bandwidth: 2000000, codecs: ['avc1'] },
    { index: 2, name: 'Audio only', resolution: null, bandwidth: 128000, codecs: [] },
  ],
  audio_tracks: [
    { group: 'a', name: 'English', language: 'en' },
    { group: 'a', name: 'Commentary', language: null },
  ],
  subtitle_tracks: [{ group: 's', name: 'French', language: 'fr' }],
  video_tracks: [],
};
const MEDIA = { type: 'media', url: 'https://x/v.m3u8', segments: 12, duration: 59.6 };

/**
 * @param {unknown} body
 * @param {number} [status]
 */
function json(body, status = 200) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) });
}

/** @param {Record<string, (init: RequestInit) => Promise<unknown>>} routes */
function mockApi(routes) {
  const handlers = new Map(Object.entries(routes));
  vi.stubGlobal(
    'fetch',
    vi.fn((/** @type {string} */ url, /** @type {RequestInit} */ init = {}) => {
      const key = `${init.method ?? 'GET'} ${url}`;
      const handler = handlers.get(key);
      return handler ? handler(init) : json({ detail: `unmocked ${key}` }, 500);
    }),
  );
}

/** @param {{ onStarted?: () => void, defaultQuality?: string }} [props] */
function renderForm(props) {
  return render(
    <StrictMode>
      <NewDownload onStarted={() => {}} {...props} />
    </StrictMode>,
  );
}

/**
 * @param {ReturnType<typeof userEvent.setup>} user
 * @param {string} [address]
 */
async function inspectStream(user, address = 'https://x/m.m3u8') {
  await user.type(screen.getByLabelText('Playlist address'), address);
  await user.click(screen.getByRole('button', { name: 'Inspect' }));
}

describe('NewDownload', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('disables Inspect until an address is entered', async () => {
    mockApi({});
    const user = userEvent.setup();
    renderForm();
    expect(screen.getByRole('button', { name: 'Inspect' })).toBeDisabled();
    await user.type(screen.getByLabelText('Playlist address'), 'https://x/m.m3u8');
    expect(screen.getByRole('button', { name: 'Inspect' })).toBeEnabled();
  });

  it('has no accessibility violations', async () => {
    mockApi({ 'POST /api/v1/inspect': () => json({ playlist: MASTER }) });
    const user = userEvent.setup();
    const { container } = renderForm();
    await inspectStream(user);
    await screen.findByText('1280x720');
    expect(await axe(container)).toHaveNoViolations();
  });

  it('lists the streams of a master playlist and only tracks with a language', async () => {
    mockApi({ 'POST /api/v1/inspect': () => json({ playlist: MASTER }) });
    const user = userEvent.setup();
    renderForm();
    await inspectStream(user);
    expect(await screen.findByText('2 streams available')).toBeInTheDocument();
    expect(screen.getByText('Audio only')).toBeInTheDocument();
    expect(screen.getByLabelText('English (en)')).toBeInTheDocument();
    expect(screen.getByLabelText('French (fr)')).toBeInTheDocument();
    expect(screen.queryByText(/Commentary/)).not.toBeInTheDocument();
  });

  it('summarises a single stream', async () => {
    mockApi({ 'POST /api/v1/inspect': () => json({ playlist: MEDIA }) });
    const user = userEvent.setup();
    renderForm();
    await inspectStream(user, 'https://x/v.m3u8');
    expect(await screen.findByText(/12 segments, 60 s/)).toBeInTheDocument();
  });

  it('shows an error when inspecting fails', async () => {
    mockApi({ 'POST /api/v1/inspect': () => json({ detail: 'Not an HLS playlist.' }, 422) });
    const user = userEvent.setup();
    renderForm();
    await inspectStream(user, 'https://x/bad');
    expect(await screen.findByRole('alert')).toHaveTextContent('Not an HLS playlist.');
    expect(screen.queryByRole('region', { name: 'Stream details' })).not.toBeInTheDocument();
  });

  it('starts a download with the chosen tracks and the default quality', async () => {
    const start = vi.fn(
      /** @type {(init: RequestInit) => Promise<unknown>} */ (() => json({ id: 'abc' }, 202)),
    );
    mockApi({
      'POST /api/v1/inspect': () => json({ playlist: MASTER }),
      'POST /api/v1/downloads': start,
    });
    const onStarted = vi.fn();
    const user = userEvent.setup();
    renderForm({ onStarted, defaultQuality: '720p' });
    await inspectStream(user);
    await user.click(await screen.findByLabelText('English (en)'));
    await user.click(screen.getByLabelText('French (fr)'));
    await user.click(screen.getByRole('button', { name: 'Download' }));
    await waitFor(() => expect(onStarted).toHaveBeenCalled());
    expect(JSON.parse(String(start.mock.calls[0][0].body))).toEqual({
      url: 'https://x/m.m3u8',
      quality: '720p',
      audio: ['en'],
      subtitles: ['fr'],
    });
    expect(screen.getByLabelText('Playlist address')).toHaveValue('');
    expect(screen.queryByRole('region', { name: 'Stream details' })).not.toBeInTheDocument();
  });

  it('lets a track be unticked again', async () => {
    mockApi({ 'POST /api/v1/inspect': () => json({ playlist: MASTER }) });
    const user = userEvent.setup();
    renderForm();
    await inspectStream(user);
    const english = await screen.findByLabelText('English (en)');
    await user.click(english);
    expect(english).toBeChecked();
    await user.click(english);
    expect(english).not.toBeChecked();
  });

  it('keeps the form and shows the error when starting fails', async () => {
    mockApi({
      'POST /api/v1/inspect': () => json({ playlist: MEDIA }),
      'POST /api/v1/downloads': () => json({ detail: 'Queue is full.' }, 429),
    });
    const onStarted = vi.fn();
    const user = userEvent.setup();
    renderForm({ onStarted });
    await inspectStream(user, 'https://x/v.m3u8');
    await user.click(await screen.findByRole('button', { name: 'Download' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Queue is full.');
    expect(onStarted).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Playlist address')).toHaveValue('https://x/v.m3u8');
  });
});
