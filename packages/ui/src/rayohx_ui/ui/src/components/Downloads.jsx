import { useCallback, useEffect, useState } from 'react';
import {
  Badge,
  Body1,
  Button,
  MessageBar,
  MessageBarBody,
  ProgressBar,
  Text,
  Title3,
  makeStyles,
  tokens,
} from '@fluentui/react-components';
import {
  Delete24Regular,
  Dismiss24Regular,
  Pause24Regular,
  Play24Regular,
} from '@fluentui/react-icons';
import { controlDownload, downloadLog, listDownloads, removeDownload } from '../api.js';
import { ACTIVE, bytes, duration, speed } from '../format.js';

const useStyles = makeStyles({
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
    justifyContent: 'space-between',
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

const BADGE = {
  downloading: { color: 'brand', appearance: 'filled' },
  paused: { color: 'warning', appearance: 'filled' },
  failed: { color: 'danger', appearance: 'filled' },
  cancelled: { color: 'danger', appearance: 'outline' },
  completed: { color: 'success', appearance: 'filled' },
};

export function StateBadge({ state }) {
  const style = BADGE[state] ?? { color: 'informative', appearance: 'tint' };
  return <Badge {...style}>{state}</Badge>;
}

function Log({ id }) {
  const [events, setEvents] = useState(null);
  useEffect(() => {
    let alive = true;
    const load = () =>
      downloadLog(id).then(
        (data) => alive && setEvents(data),
        () => {},
      );
    load();
    const timer = setInterval(load, 2000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [id]);
  if (!events) return null;
  return (
    <ol aria-label="Engine log" style={{ margin: 0, paddingLeft: '1.25rem' }}>
      {events.map((e, i) => (
        <li key={`${e.time}-${i}`}>
          <code>{new Date(e.time * 1000).toLocaleTimeString()}</code> {e.type.replaceAll('_', ' ')}
          {e.segment != null && ` (segment ${e.segment})`}
          {e.message && `: ${e.message}`}
        </li>
      ))}
    </ol>
  );
}

export default function Downloads({ onCount }) {
  const styles = useStyles();
  const [items, setItems] = useState([]);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const data = await listDownloads();
      setItems(data.items);
      onCount?.(data.items.filter((j) => ACTIVE.includes(j.state)).length);
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

  async function act(task) {
    try {
      await task();
    } catch (problem) {
      setError(problem.message);
    }
    refresh();
  }

  return (
    <div>
      <Title3 as="h2">Downloads</Title3>
      {error && (
        <MessageBar intent="error" role="alert">
          <MessageBarBody>{error}</MessageBarBody>
        </MessageBar>
      )}
      {items.length === 0 ? (
        <Body1 as="p">Nothing here yet. Add a stream to get started.</Body1>
      ) : (
        <ul className={styles.list}>
          {items.map((job) => {
            const p = job.progress;
            const running = ACTIVE.includes(job.state);
            return (
              <li key={job.id} className={styles.item}>
                <div className={styles.top}>
                  <Text weight="semibold" className={styles.url} title={job.url}>
                    {job.output_path ?? job.url}
                  </Text>
                  <StateBadge state={job.state} />
                  <div className={styles.actions}>
                    {job.state === 'downloading' && (
                      <Button
                        icon={<Pause24Regular />}
                        appearance="subtle"
                        aria-label={`Pause ${job.id}`}
                        onClick={() => act(() => controlDownload(job.id, 'pause'))}
                      />
                    )}
                    {job.state === 'paused' && (
                      <Button
                        icon={<Play24Regular />}
                        appearance="subtle"
                        aria-label={`Resume ${job.id}`}
                        onClick={() => act(() => controlDownload(job.id, 'resume'))}
                      />
                    )}
                    {running ? (
                      <Button
                        icon={<Dismiss24Regular />}
                        appearance="subtle"
                        aria-label={`Cancel ${job.id}`}
                        onClick={() => act(() => controlDownload(job.id, 'cancel'))}
                      />
                    ) : (
                      <Button
                        icon={<Delete24Regular />}
                        appearance="subtle"
                        aria-label={`Remove ${job.id}`}
                        onClick={() => act(() => removeDownload(job.id))}
                      />
                    )}
                  </div>
                </div>
                {running && (
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
                </div>
                <Button
                  size="small"
                  appearance="transparent"
                  onClick={() => setOpen(open === job.id ? null : job.id)}
                >
                  {open === job.id ? 'Hide log' : 'Show log'}
                </Button>
                {open === job.id && <Log id={job.id} />}
                {job.error && (
                  <MessageBar intent="error">
                    <MessageBarBody>{job.error}</MessageBarBody>
                  </MessageBar>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
