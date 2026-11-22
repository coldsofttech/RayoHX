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
  Tooltip,
  makeStyles,
  tokens,
} from '@fluentui/react-components';
import {
  ArrowClockwise24Regular,
  Broom24Regular,
  Delete24Regular,
  Dismiss24Regular,
  Pause24Regular,
  Play24Regular,
} from '@fluentui/react-icons';
import {
  clearDownloads,
  controlDownload,
  errorMessage,
  listDownloads,
  removeDownload,
} from '../api.js';
import { ACTIVE, bytes, duration, speed } from '../format.js';

const useStyles = makeStyles({
  card: {
    backgroundColor: tokens.colorNeutralBackground1,
    border: `1px solid ${tokens.colorNeutralStroke2}`,
    borderRadius: tokens.borderRadiusXLarge,
    boxShadow: tokens.shadow4,
    padding: tokens.spacingHorizontalXL,
    display: 'flex',
    flexDirection: 'column',
    rowGap: tokens.spacingVerticalM,
  },
  header: { display: 'flex', alignItems: 'center', justifyContent: 'space-between' },
  heading: { margin: 0 },
  list: {
    display: 'flex',
    flexDirection: 'column',
    rowGap: tokens.spacingVerticalM,
    padding: 0,
    margin: 0,
    listStyle: 'none',
  },
  item: {
    backgroundColor: tokens.colorNeutralBackground2,
    border: `1px solid ${tokens.colorNeutralStroke2}`,
    borderRadius: tokens.borderRadiusLarge,
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

/** @type {Map<string, import('@fluentui/react-components').BadgeProps>} */
const BADGE = new Map([
  ['downloading', { color: 'brand', appearance: 'filled' }],
  ['paused', { color: 'warning', appearance: 'filled' }],
  ['failed', { color: 'danger', appearance: 'filled' }],
  ['cancelled', { color: 'danger', appearance: 'outline' }],
  ['completed', { color: 'success', appearance: 'filled' }],
]);

/** @param {{ state: string }} props */
export function StateBadge({ state }) {
  /** @type {import('@fluentui/react-components').BadgeProps} */
  const style = BADGE.get(state) ?? { color: 'informative', appearance: 'tint' };
  return <Badge {...style}>{state}</Badge>;
}

/**
 * @typedef {object} Job
 * @property {string} id
 * @property {string} url
 * @property {string} state
 * @property {string} [output_path]
 * @property {number | null} [output_size_bytes]
 * @property {string | null} [error]
 * @property {{ fraction: number | null, speed: number | null, eta_seconds: number | null } | null} [progress]
 */

/** @param {{ onCount?: (active: number) => void }} props */
export default function Downloads({ onCount }) {
  const styles = useStyles();
  const [items, setItems] = useState(/** @type {Job[]} */ ([]));
  const [loadError, setLoadError] = useState('');
  const [actionError, setActionError] = useState('');

  const refresh = useCallback(async () => {
    try {
      const data = await listDownloads();
      setItems(data.items);
      onCount?.(data.items.filter((/** @type {Job} */ j) => ACTIVE.includes(j.state)).length);
      setLoadError('');
    } catch (problem) {
      setLoadError(errorMessage(problem));
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

  /** @param {() => Promise<unknown>} task */
  async function act(task) {
    try {
      await task();
      setActionError('');
    } catch (problem) {
      setActionError(errorMessage(problem));
    }
    refresh();
  }

  // A failed control stays visible; the list refreshing every second must not clear it.
  const error = actionError || loadError;

  return (
    <section className={styles.card} aria-label="Downloads">
      <div className={styles.header}>
        <Title3 as="h2" className={styles.heading}>
          Downloads
        </Title3>
        {items.some((job) => !ACTIVE.includes(job.state)) && (
          <Tooltip content="Clear history" relationship="label">
            <Button
              icon={<Broom24Regular />}
              appearance="subtle"
              onClick={() => act(clearDownloads)}
            />
          </Tooltip>
        )}
      </div>
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
                  {job.quality && (
                    <Badge appearance="outline" color="informative">
                      {job.quality}
                    </Badge>
                  )}
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
                    {job.retryable && (
                      <Button
                        icon={<ArrowClockwise24Regular />}
                        appearance="subtle"
                        aria-label={`Retry ${job.id}`}
                        onClick={() => act(() => controlDownload(job.id, 'retry'))}
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
    </section>
  );
}
