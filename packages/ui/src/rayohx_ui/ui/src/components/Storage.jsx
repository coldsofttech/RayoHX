import { useCallback, useEffect, useState } from 'react';
import {
  Body1,
  Button,
  Field,
  Input,
  MessageBar,
  MessageBarBody,
  Switch,
  Title3,
  makeStyles,
  tokens,
} from '@fluentui/react-components';
import { setStoragePolicy, storageCleanup, storageStatus, storageWorkspaces } from '../api.js';
import { bytes } from '../format.js';

const useStyles = makeStyles({
  card: {
    backgroundColor: tokens.colorNeutralBackground1,
    border: `1px solid ${tokens.colorNeutralStroke2}`,
    borderRadius: tokens.borderRadiusXLarge,
    padding: tokens.spacingHorizontalL,
    marginTop: tokens.spacingVerticalL,
    display: 'flex',
    flexDirection: 'column',
    rowGap: tokens.spacingVerticalS,
  },
  row: { display: 'flex', flexWrap: 'wrap', columnGap: tokens.spacingHorizontalM },
});

const FIELDS = [
  ['warn_below', 'Warn below'],
  ['pause_below', 'Pause below'],
  ['stop_below', 'Stop below'],
];

export default function Storage() {
  const styles = useStyles();
  const [status, setStatus] = useState(null);
  const [folders, setFolders] = useState([]);
  const [form, setForm] = useState(null);
  const [plan, setPlan] = useState(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const [s, w] = await Promise.all([storageStatus(), storageWorkspaces()]);
      setStatus(s);
      setFolders(w);
      setForm(
        (now) =>
          now ?? {
            warn_below: s.policy.warn_below ?? '',
            pause_below: s.policy.pause_below ?? '',
            stop_below: s.policy.stop_below ?? '',
            low_storage_mode: s.policy.low_storage_mode,
          },
      );
      setError('');
    } catch (problem) {
      setError(problem.message);
    }
  }, []);

  useEffect(() => {
    const first = setTimeout(load, 0);
    return () => clearTimeout(first);
  }, [load]);

  async function savePolicy() {
    const body = { low_storage_mode: form.low_storage_mode };
    for (const [key] of FIELDS) body[key] = form[key] === '' ? null : form[key];
    try {
      await setStoragePolicy(body);
      setMessage('The policy was saved.');
      setError('');
      load();
    } catch (problem) {
      setError(problem.message);
    }
  }

  async function cleanup(dryRun) {
    try {
      const result = await storageCleanup({ dry_run: dryRun });
      setPlan(result);
      setMessage(
        dryRun
          ? `Would free ${bytes(result.plan.total_bytes)}.`
          : `Freed ${bytes(result.freed_bytes)}.`,
      );
      if (!dryRun) load();
    } catch (problem) {
      setError(problem.message);
    }
  }

  const downloads = status?.volumes.find((v) => v.role === 'downloads');
  return (
    <div>
      <Title3 as="h2">Storage</Title3>
      {error && (
        <MessageBar intent="error" role="alert">
          <MessageBarBody>{error}</MessageBarBody>
        </MessageBar>
      )}
      {message && (
        <MessageBar intent="success">
          <MessageBarBody>{message}</MessageBarBody>
        </MessageBar>
      )}
      {status && (
        <section className={styles.card} aria-label="Disk space">
          <Body1>
            Level: <strong>{status.level}</strong>
            {downloads && (
              <>
                . {bytes(downloads.free_bytes)} free of {bytes(downloads.total_bytes)}.
              </>
            )}
          </Body1>
          <Body1>
            Finished downloads {bytes(status.output_bytes)}. Working folders{' '}
            {bytes(status.workspace_bytes)} ({status.workspace_count}), of which{' '}
            {bytes(status.incomplete_bytes)} belongs to no finished download. Reserved{' '}
            {bytes(status.reserved_bytes)}.
          </Body1>
        </section>
      )}
      {form && (
        <section className={styles.card} aria-label="Low-space policy">
          <Body1>
            When free space falls under a limit, running downloads wait (and go on by themselves) or
            stop. Use sizes such as 5GB; leave a limit empty to turn it off.
          </Body1>
          <div className={styles.row}>
            {FIELDS.map(([key, label]) => (
              <Field key={key} label={label}>
                <Input
                  value={String(form[key])}
                  onChange={(_, d) => setForm({ ...form, [key]: d.value })}
                />
              </Field>
            ))}
          </div>
          <Switch
            label="Low-storage mode"
            checked={form.low_storage_mode}
            onChange={(_, d) => setForm({ ...form, low_storage_mode: d.checked })}
          />
          <div>
            <Button appearance="primary" onClick={savePolicy}>
              Save policy
            </Button>
          </div>
        </section>
      )}
      <section className={styles.card} aria-label="Working folders">
        <Body1>
          Leftovers of interrupted downloads. Cleaning never touches finished downloads or folders a
          download can still continue from.
        </Body1>
        {folders.length === 0 ? (
          <Body1>There are no working folders.</Body1>
        ) : (
          <ul>
            {folders.map((f) => (
              <li key={f.name}>
                {f.name}, {bytes(f.size_bytes)},{' '}
                {f.in_use ? 'in use' : f.safe_to_remove ? 'can be removed' : 'kept'}
                {f.reason && ` (${f.reason})`}
              </li>
            ))}
          </ul>
        )}
        {plan?.plan.items.length > 0 && (
          <ul aria-label="To be removed">
            {plan.plan.items.map((i) => (
              <li key={`${i.kind}-${i.name}`}>
                {i.kind} {i.name}, {bytes(i.size_bytes)}
              </li>
            ))}
          </ul>
        )}
        <div className={styles.row}>
          <Button onClick={() => cleanup(true)}>Preview cleanup</Button>
          <Button disabled={!plan || plan.plan.items.length === 0} onClick={() => cleanup(false)}>
            Remove what was previewed
          </Button>
        </div>
      </section>
    </div>
  );
}
