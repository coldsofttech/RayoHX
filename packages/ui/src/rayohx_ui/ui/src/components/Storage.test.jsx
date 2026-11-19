import { afterEach, describe, expect, it, vi } from 'vitest';
import { axe } from 'vitest-axe';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Storage from './Storage.jsx';

const STATUS = {
  level: 'ok',
  volumes: [{ role: 'downloads', free_bytes: 5 * 1024 ** 3, total_bytes: 10 * 1024 ** 3 }],
  output_bytes: 1024,
  workspace_bytes: 2048,
  workspace_count: 1,
  incomplete_bytes: 2048,
  reserved_bytes: 0,
  policy: { warn_below: null, pause_below: 1024 ** 3, stop_below: null, low_storage_mode: false },
};
const FOLDER = {
  name: '.rayohx-old',
  size_bytes: 2048,
  in_use: false,
  safe_to_remove: true,
  reason: 'left over',
};

function reply(body, status = 200) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) });
}

function mockApi(extra = {}) {
  const sent = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((url, init = {}) => {
      const key = `${init.method ?? 'GET'} ${url}`;
      if (init.body) sent.push([key, JSON.parse(init.body)]);
      if (key === 'GET /api/v2/storage') return reply(STATUS);
      if (key === 'GET /api/v2/storage/workspaces') return reply([FOLDER]);
      const handler = extra[key];
      return handler ? handler(init) : reply({ detail: `unmocked ${key}` }, 500);
    }),
  );
  return sent;
}

describe('Storage', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('shows space, the policy and the working folders', async () => {
    mockApi();
    render(<Storage />);
    expect(await screen.findByText(/5.0 GB free of 10.0 GB/)).toBeInTheDocument();
    expect(screen.getByLabelText('Pause below')).toHaveValue('1073741824');
    expect(screen.getByText(/\.rayohx-old, 2.0 KB, can be removed/)).toBeInTheDocument();
  });

  it('saves the policy, sending empty limits as off', async () => {
    const sent = mockApi({ 'PUT /api/v2/storage/policy': () => reply({}) });
    const user = userEvent.setup();
    render(<Storage />);
    const warn = await screen.findByLabelText('Warn below');
    await user.type(warn, '10GB');
    await user.click(screen.getByRole('switch', { name: 'Low-storage mode' }));
    await user.click(screen.getByRole('button', { name: 'Save policy' }));
    await waitFor(() => expect(sent.length).toBeGreaterThan(0));
    expect(sent[0][1]).toEqual({
      warn_below: '10GB',
      pause_below: 1073741824,
      stop_below: null,
      low_storage_mode: true,
    });
    expect(await screen.findByText('The policy was saved.')).toBeInTheDocument();
  });

  it('previews a cleanup before removing anything', async () => {
    const sent = mockApi({
      'POST /api/v2/storage/cleanup': (init) => {
        const dry = JSON.parse(init.body).dry_run;
        const item = { kind: 'workspace', name: '.rayohx-old', size_bytes: 2048 };
        return reply({
          plan: { items: [item], total_bytes: 2048, kept: [] },
          freed_bytes: dry ? 0 : 2048,
        });
      },
    });
    const user = userEvent.setup();
    render(<Storage />);
    const remove = await screen.findByRole('button', { name: 'Remove what was previewed' });
    expect(remove).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Preview cleanup' }));
    expect(await screen.findByText('Would free 2.0 KB.')).toBeInTheDocument();
    expect(remove).toBeEnabled();
    await user.click(remove);
    expect(await screen.findByText('Freed 2.0 KB.')).toBeInTheDocument();
    expect(sent.filter(([key]) => key.includes('cleanup')).map(([, b]) => b.dry_run)).toEqual([
      true,
      false,
    ]);
  });

  it('has no accessibility violations', async () => {
    mockApi();
    const { container } = render(<Storage />);
    await screen.findByLabelText('Warn below');
    expect(await axe(container)).toHaveNoViolations();
  });
});
