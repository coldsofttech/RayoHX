import { StrictMode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { axe } from 'vitest-axe';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Settings from './Settings.jsx';

const SETTINGS = {
  download_dir: '/d',
  max_active_downloads: 2,
  allow_local_paths: true,
  concurrency: 4,
  quality: 'best',
  overwrite: false,
  limits: { min_concurrency: 1, max_concurrency: 64 },
  version: '0.1.0',
};

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

/**
 * A recorded route: ``json(body)`` for every call, typed so the request can be read back.
 * @param {unknown} body
 */
const route = (body) =>
  vi.fn(/** @type {(init: RequestInit) => Promise<unknown>} */ (() => json(body)));

/** @param {{ mock: { calls: RequestInit[][] } }} handler The request body of its first call. */
const sentBody = (handler) => JSON.parse(String(handler.mock.calls[0][0].body));

/** @param {{ onChanged?: (settings: unknown) => void }} [props] */
function renderSettings(props) {
  return render(
    <StrictMode>
      <Settings {...props} />
    </StrictMode>,
  );
}

describe('Settings', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('shows the current settings', async () => {
    mockApi({ 'GET /api/v1/settings': () => json(SETTINGS) });
    renderSettings();
    expect(await screen.findByText('Parallel segments: 4')).toBeInTheDocument();
    expect(screen.getByText('/d')).toBeInTheDocument();
    expect(screen.getByText(/Version 0\.1\.0/)).toBeInTheDocument();
    expect(screen.getByLabelText('Default quality')).toHaveValue('best');
    expect(
      screen.getByRole('switch', { name: 'Replace files that already exist' }),
    ).not.toBeChecked();
  });

  it('lets the slider span the range the API reports', async () => {
    mockApi({
      'GET /api/v1/settings': () =>
        json({ ...SETTINGS, limits: { min_concurrency: 2, max_concurrency: 32 } }),
    });
    renderSettings();
    const slider = await screen.findByRole('slider');
    expect(slider).toHaveAttribute('min', '2');
    expect(slider).toHaveAttribute('max', '32');
  });

  it('has no accessibility violations', async () => {
    mockApi({ 'GET /api/v1/settings': () => json(SETTINGS) });
    const { container } = renderSettings();
    await screen.findByText('Parallel segments: 4');
    expect(await axe(container)).toHaveNoViolations();
  });

  it('shows an error when the settings cannot be loaded', async () => {
    mockApi({ 'GET /api/v1/settings': () => json({ detail: 'Server down.' }, 500) });
    renderSettings();
    expect(await screen.findByRole('alert')).toHaveTextContent('Server down.');
    expect(screen.queryByText('Defaults')).not.toBeInTheDocument();
  });

  it('saves a changed setting and tells the parent', async () => {
    const patch = route({ ...SETTINGS, overwrite: true });
    mockApi({ 'GET /api/v1/settings': () => json(SETTINGS), 'PATCH /api/v1/settings': patch });
    const onChanged = vi.fn();
    const user = userEvent.setup();
    renderSettings({ onChanged });
    await user.click(
      await screen.findByRole('switch', { name: 'Replace files that already exist' }),
    );
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith({ ...SETTINGS, overwrite: true }));
    expect(sentBody(patch)).toEqual({ overwrite: true });
    expect(screen.getByRole('switch', { name: 'Replace files that already exist' })).toBeChecked();
  });

  it('saves the default quality', async () => {
    const patch = route({ ...SETTINGS, quality: '720p' });
    mockApi({ 'GET /api/v1/settings': () => json(SETTINGS), 'PATCH /api/v1/settings': patch });
    const user = userEvent.setup();
    renderSettings();
    await user.click(await screen.findByLabelText('Default quality'));
    await user.click(await screen.findByRole('option', { name: '720p' }));
    await waitFor(() => expect(patch).toHaveBeenCalled());
    expect(sentBody(patch)).toEqual({ quality: '720p' });
  });

  it('shows an error when saving fails', async () => {
    mockApi({
      'GET /api/v1/settings': () => json(SETTINGS),
      'PATCH /api/v1/settings': () => json({ detail: 'Not allowed.' }, 403),
    });
    const user = userEvent.setup();
    renderSettings();
    await user.click(
      await screen.findByRole('switch', { name: 'Replace files that already exist' }),
    );
    expect(await screen.findByRole('alert')).toHaveTextContent('Not allowed.');
  });

  it('shows the clean up and about cards under the settings', async () => {
    mockApi({ 'GET /api/v1/settings': () => json(SETTINGS) });
    renderSettings();
    await screen.findByText('Parallel segments: 4');
    expect(screen.getByRole('region', { name: 'Settings' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Clean up' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'About' })).toBeInTheDocument();
  });

  it('saves the folder picked in the window', async () => {
    const patch = route({ ...SETTINGS, download_dir: '/new' });
    const pick = route({ result: '/new' });
    mockApi({
      'GET /api/v1/settings': () => json(SETTINGS),
      'POST /api/bridge/choose_folder': pick,
      'PATCH /api/v1/settings': patch,
    });
    const user = userEvent.setup();
    renderSettings();
    await user.click(await screen.findByRole('button', { name: 'Change' }));
    expect(await screen.findByText('/new')).toBeInTheDocument();
    expect(sentBody(pick)).toEqual({ directory: '/d' });
    expect(sentBody(patch)).toEqual({ download_dir: '/new' });
  });

  it('keeps the folder when the dialog is closed', async () => {
    const patch = route(SETTINGS);
    mockApi({
      'GET /api/v1/settings': () => json(SETTINGS),
      'POST /api/bridge/choose_folder': () => json({ result: null }),
      'PATCH /api/v1/settings': patch,
    });
    const user = userEvent.setup();
    renderSettings();
    await user.click(await screen.findByRole('button', { name: 'Change' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Change' })).toBeEnabled());
    expect(patch).not.toHaveBeenCalled();
    expect(screen.getByText('/d')).toBeInTheDocument();
  });

  it('shows an error when the folder picker is not available', async () => {
    mockApi({
      'GET /api/v1/settings': () => json(SETTINGS),
      'POST /api/bridge/choose_folder': () => json({ available: false, reason: 'No window.' }),
    });
    const user = userEvent.setup();
    renderSettings();
    await user.click(await screen.findByRole('button', { name: 'Change' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('No window.');
  });
});
