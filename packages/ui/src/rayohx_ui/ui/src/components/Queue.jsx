import { useCallback, useEffect, useState } from 'react';
import {
  Badge,
  Body1,
  Button,
  Checkbox,
  Dropdown,
  MessageBar,
  MessageBarBody,
  Option,
  ProgressBar,
  Text,
  Title3,
  makeStyles,
  tokens,
} from '@fluentui/react-components';
import {
  ArrowDown24Regular,
  ArrowUp24Regular,
  Pause24Regular,
  Play24Regular,
} from '@fluentui/react-icons';
import { queueAction, queueList } from '../api.js';
import { ACTIVE, bytes, duration, speed } from '../format.js';
import JobDetails from './JobDetails.jsx';
import StateBadge from './StateBadge.jsx';

const useStyles = makeStyles({
  toolbar: {
    display: 'flex',
    flexWrap: 'wrap',
    alignItems: 'center',
    columnGap: tokens.spacingHorizontalS,
    rowGap: tokens.spacingVerticalS,
    margin: `${tokens.spacingVerticalM} 0`,
  },
  list: {
    display: 'flex',
    flexDirection: 'column',
    rowGap: tokens.spacingVerticalM,
    padding: 0,
    margin: 0,
    listStyle: 'none',
  },
  item: {
    backgroundColor: tokens.colorNeutralBackground1,
    border: `1px solid ${tokens.colorNeutralStroke2}`,
    borderRadius: tokens.borderRadiusXLarge,
    boxShadow: tokens.shadow4,
    padding: tokens.spacingHorizontalL,
    display: 'flex',
    flexDirection: 'column',
    rowGap: tokens.spacingVerticalS,
  },
  top: {
    display: 'flex',
    alignItems: 'center',
    columnGap: tokens.spacingHorizontalM,
  },
  url: {
    flexGrow: 1,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    minWidth: 0,
  },
  meta: {
    display: 'flex',
    columnGap: tokens.spacingHorizontalL,
    color: tokens.colorNeutralForeground3,
  },
  actions: { display: 'flex', columnGap: tokens.spacingHorizontalXS, flexShrink: 0 },
});

const PRIORITIES = ['low', 'normal', 'high'];
const BULK = [
  ['pause', 'Pause'],
  ['resume', 'Resume'],
  ['cancel', 'Cancel'],
  ['retry', 'Retry'],
  ['remove', 'Remove'],
];

export default function Queue({ onCount }) {
  const styles = useStyles();
  const [data, setData] = useState({ items: [], stats: null });
  const [selected, setSelected] = useState(new Set());
  const [priority, setPriority] = useState('normal');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [open, setOpen] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const next = await queueList();
      setData(next);
      onCount?.(next.items.filter((j) => ACTIVE.includes(j.state)).length);
      setSelected((now) => new Set([...now].filter((id) => next.items.some((j) => j.id === id))));
      setError('');
    } catch (problem) {
      setError(problem.message);
    }
  }, [onCount]);

  useEffect(() => {
    const first = setTimeout(refresh, 0);
    const timer = setInterval(refresh, 1000);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, [refresh]);

  async function act(action, ids, extra) {
    try {
      const result = await queueAction(action, ids, extra);
      const failed = Object.entries(result.failed);
      setNotice(failed.length ? `${failed.length} not changed: ${failed[0][1]}` : '');
    } catch (problem) {
      setError(problem.message);
    }
    refresh();
  }

  const ids = [...selected];
  const all = data.items.length > 0 && selected.size === data.items.length;
  const toggle = (id, on) =>
    setSelected((now) => {
      const next = new Set(now);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });

  return (
    <div>
      <Title3 as="h2">Queue</Title3>
      {data.stats && (
        <Body1 as="p">
          {data.stats.active} running of {data.stats.max_active} at once, {data.stats.counts.queued}{' '}
          waiting.
        </Body1>
      )}
      {error && (
        <MessageBar intent="error" role="alert">
          <MessageBarBody>{error}</MessageBarBody>
        </MessageBar>
      )}
      {notice && (
        <MessageBar intent="warning">
          <MessageBarBody>{notice}</MessageBarBody>
        </MessageBar>
      )}
      {data.items.length === 0 ? (
        <Body1 as="p">Nothing here yet. Add a stream to get started.</Body1>
      ) : (
        <>
          <div className={styles.toolbar} role="toolbar" aria-label="Actions for selected jobs">
            <Checkbox
              label="Select all"
              checked={all}
              onChange={(_, d) =>
                setSelected(d.checked ? new Set(data.items.map((j) => j.id)) : new Set())
              }
            />
            {BULK.map(([action, label]) => (
              <Button
                key={action}
                size="small"
                disabled={ids.length === 0}
                onClick={() => act(action, ids)}
              >
                {label}
              </Button>
            ))}
            <Dropdown
              aria-label="Priority"
              value={priority}
              selectedOptions={[priority]}
              onOptionSelect={(_, d) => setPriority(d.optionValue)}
              style={{ minWidth: '7rem' }}
            >
              {PRIORITIES.map((p) => (
                <Option key={p} value={p}>
                  {p}
                </Option>
              ))}
            </Dropdown>
            <Button
              size="small"
              disabled={ids.length === 0}
              onClick={() => act('priority', ids, { priority })}
            >
              Set priority
            </Button>
          </div>
          <ul className={styles.list}>
            {data.items.map((job) => {
              const p = job.progress;
              const running = ACTIVE.includes(job.state);
              return (
                <li key={job.id} className={styles.item}>
                  <div className={styles.top}>
                    <Checkbox
                      aria-label={`Select ${job.id}`}
                      checked={selected.has(job.id)}
                      onChange={(_, d) => toggle(job.id, d.checked)}
                    />
                    <Text weight="semibold" className={styles.url} title={job.url}>
                      {job.output_path ?? job.url}
                    </Text>
                    <Badge appearance="outline" color="informative">
                      {job.priority}
                    </Badge>
                    <StateBadge state={job.state} />
                    <div className={styles.actions}>
                      {job.state === 'downloading' && (
                        <Button
                          icon={<Pause24Regular />}
                          appearance="subtle"
                          aria-label={`Pause ${job.id}`}
                          onClick={() => act('pause', [job.id])}
                        />
                      )}
                      {job.state === 'paused' && (
                        <Button
                          icon={<Play24Regular />}
                          appearance="subtle"
                          aria-label={`Resume ${job.id}`}
                          onClick={() => act('resume', [job.id])}
                        />
                      )}
                      {job.state === 'queued' && (
                        <>
                          <Button
                            icon={<ArrowUp24Regular />}
                            appearance="subtle"
                            aria-label={`Move ${job.id} to the top`}
                            onClick={() => act('top', [job.id])}
                          />
                          <Button
                            icon={<ArrowDown24Regular />}
                            appearance="subtle"
                            aria-label={`Move ${job.id} to the bottom`}
                            onClick={() => act('bottom', [job.id])}
                          />
                        </>
                      )}
                    </div>
                  </div>
                  {running && job.state !== 'queued' && (
                    <ProgressBar
                      value={p?.fraction ?? undefined}
                      color={job.state === 'paused' ? 'warning' : 'brand'}
                      aria-label="Download progress"
                    />
                  )}
                  <div className={styles.meta}>
                    {p && running && (
                      <>
                        <span>{Math.round((p.fraction ?? 0) * 100)}%</span>
                        <span>{speed(p.speed)}</span>
                        <span>ETA {duration(p.eta_seconds)}</span>
                      </>
                    )}
                    {job.output_size_bytes != null && <span>{bytes(job.output_size_bytes)}</span>}
                    {job.attempts > 1 && (
                      <span>
                        run {job.attempts} of {job.max_attempts}
                      </span>
                    )}
                    {job.verification !== 'not_requested' && (
                      <span>verification: {job.verification}</span>
                    )}
                  </div>
                  {job.error && (
                    <MessageBar intent="error">
                      <MessageBarBody>{job.error}</MessageBarBody>
                    </MessageBar>
                  )}
                  <Button
                    size="small"
                    appearance="transparent"
                    aria-expanded={open === job.id}
                    onClick={() => setOpen(open === job.id ? null : job.id)}
                  >
                    {open === job.id ? 'Hide details' : 'Show details'}
                  </Button>
                  {open === job.id && <JobDetails job={job} />}
                </li>
              );
            })}
          </ul>
        </>
      )}
    </div>
  );
}
