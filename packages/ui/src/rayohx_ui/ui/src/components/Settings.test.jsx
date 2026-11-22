import { StrictMode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { axe } from 'vitest-axe';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Settings from './Settings.jsx';

const SETTINGS = {
  download_dir: '/d',
  max_active_downloads: 2,
  concurrency: 4,
  quality: 'best',
  overwrite: false,
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

  it('previews what a clean up would remove', async () => {
    const sweep = route({
      dry_run: true,
      folders: ['a', 'b'],
      freed_bytes: 2048,
      skipped_in_use: 1,
    });
    mockApi({ 'GET /api/v1/settings': () => json(SETTINGS), 'POST /api/v1/clean': sweep });
    const user = userEvent.setup();
    renderSettings();
    await user.click(await screen.findByRole('button', { name: 'Preview' }));
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Would remove 2 folder(s), 2.0 KB. 1 in use were skipped.',
    );
    expect(sentBody(sweep)).toEqual({ dry_run: true });
  });

  it('removes leftovers and reports when there is nothing to clean', async () => {
    const sweep = route({ dry_run: false, folders: [], freed_bytes: 0, skipped_in_use: 0 });
    mockApi({ 'GET /api/v1/settings': () => json(SETTINGS), 'POST /api/v1/clean': sweep });
    const user = userEvent.setup();
    renderSettings();
    await user.click(await screen.findByRole('button', { name: 'Remove leftovers' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Nothing to clean.');
    expect(sentBody(sweep)).toEqual({ dry_run: false });
  });

  it('shows an error when the clean up fails', async () => {
    mockApi({
      'GET /api/v1/settings': () => json(SETTINGS),
      'POST /api/v1/clean': () => json({ detail: 'Clean up failed.' }, 500),
    });
    const user = userEvent.setup();
    renderSettings();
    await user.click(await screen.findByRole('button', { name: 'Preview' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Clean up failed.');
  });
});
