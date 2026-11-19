import { afterEach, describe, expect, it, vi } from 'vitest';
import { axe } from 'vitest-axe';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Queue from './Queue.jsx';

function job(id, extra = {}) {
  return {
    id,
    url: `https://x/${id}.m3u8`,
    state: 'queued',
    priority: 'normal',
    verification: 'not_requested',
    attempts: 1,
    max_attempts: 3,
    ...extra,
  };
}

function reply(body, status = 200) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) });
}

function mockApi(items, extra = {}) {
  const posts = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((url, init = {}) => {
      const key = `${init.method ?? 'GET'} ${url}`;
      if (key === 'GET /api/v2/queue') {
        return reply({
          items,
          stats: { counts: { queued: items.length }, active: 0, max_active: 2 },
        });
      }
      if (key === 'POST /api/v2/queue/actions') {
        const body = JSON.parse(init.body);
        posts.push(body);
        return reply({ done: body.ids, failed: extra.failed ?? {} });
      }
      const handler = extra[key];
      return handler ? handler(init) : reply({ detail: `unmocked ${key}` }, 500);
    }),
  );
  return posts;
}

describe('Queue', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('applies an action to the selected jobs only', async () => {
    const posts = mockApi([job('a'), job('b'), job('c')]);
    const user = userEvent.setup();
    render(<Queue />);
    await user.click(await screen.findByLabelText('Select a'));
    await user.click(screen.getByLabelText('Select c'));
    await user.click(screen.getByRole('button', { name: 'Pause' }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]).toEqual({ action: 'pause', ids: ['a', 'c'] });
  });

  it('selects all and sets a priority', async () => {
    const posts = mockApi([job('a'), job('b')]);
    const user = userEvent.setup();
    render(<Queue />);
    await user.click(await screen.findByLabelText('Select all'));
    await user.click(screen.getByRole('combobox', { name: 'Priority' }));
    await user.click(await screen.findByRole('option', { name: 'high' }));
    await user.click(screen.getByRole('button', { name: 'Set priority' }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]).toEqual({ action: 'priority', ids: ['a', 'b'], priority: 'high' });
  });

  it('disables bulk actions until something is selected', async () => {
    mockApi([job('a')]);
    render(<Queue />);
    expect(await screen.findByRole('button', { name: 'Retry' })).toBeDisabled();
  });

  it('moves a waiting job to the top', async () => {
    const posts = mockApi([job('a'), job('b')]);
    const user = userEvent.setup();
    render(<Queue />);
    await user.click(await screen.findByRole('button', { name: 'Move b to the top' }));
    await waitFor(() => expect(posts[0]).toEqual({ action: 'top', ids: ['b'] }));
  });

  it('says which jobs an action did not change', async () => {
    mockApi([job('a')], { failed: { a: 'Only a failed or cancelled job can be retried.' } });
    const user = userEvent.setup();
    render(<Queue />);
    await user.click(await screen.findByLabelText('Select a'));
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText(/1 not changed: Only a failed/)).toBeInTheDocument();
  });

  it('explains a failed job and its verification', async () => {
    mockApi([job('f', { state: 'failed', verification: 'failed', error: 'bad' })], {
      'GET /api/v2/queue/f': () =>
        reply({ attempt_history: [{ attempt: 1, outcome: 'failed', error_code: 'HTTP_403' }] }),
      'GET /api/v2/queue/f/verification': () =>
        reply({
          status: 'failed',
          level: 'strong',
          segments_checked: 3,
          checks: [{ name: 'container structure', status: 'failed', detail: 'truncated' }],
          notes: [],
        }),
      'GET /api/v2/diagnostics/jobs/f': () =>
        reply({
          explanation: {
            title: 'The server refused access',
            what_happened: 'It answered 403.',
            likely_cause: 'The link expired.',
            what_was_tried: '',
            next_steps: ['Copy the address again.'],
          },
        }),
      'GET /api/v2/events?job_id=f&limit=100': () => reply({ items: [] }),
      'POST /api/v2/diagnostics/report': () => reply({ path: 'rayohx-report-1.json' }),
    });
    const user = userEvent.setup();
    render(<Queue />);
    await user.click(await screen.findByRole('button', { name: 'Show details' }));
    expect(await screen.findByText(/The server refused access/)).toBeInTheDocument();
    expect(screen.getByText('Copy the address again.')).toBeInTheDocument();
    expect(
      await screen.findByText(/container structure: failed \(truncated\)/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Run 1: failed \(HTTP_403\)/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Save a report to share' }));
    expect(await screen.findByText(/rayohx-report-1.json/)).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    mockApi([job('a'), job('b', { state: 'downloading', progress: { fraction: 0.2 } })]);
    const { container } = render(<Queue />);
    await screen.findByLabelText('Select a');
    expect(await axe(container)).toHaveNoViolations();
  });
});
