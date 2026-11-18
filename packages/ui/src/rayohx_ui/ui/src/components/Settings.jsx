import { useState } from 'react';
import {
  Body1,
  Button,
  MessageBar,
  MessageBarBody,
  Text,
  Title3,
  makeStyles,
  tokens,
} from '@fluentui/react-components';
import { clean, saveDefaults } from '../api.js';
import { bytes } from '../format.js';
import { buildOptions, toValues } from '../options.js';
import Options from './Options.jsx';

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
    marginBottom: tokens.spacingVerticalL,
  },
  row: { display: 'flex', columnGap: tokens.spacingHorizontalM },
});

export default function Settings({ settings, onChanged }) {
  const styles = useStyles();
  const [values, setValues] = useState(() => toValues(settings.defaults));
  const [report, setReport] = useState(null);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');

  async function save() {
    try {
      const next = await saveDefaults(buildOptions(values));
      onChanged(next);
      setValues(toValues(next.defaults));
      setSaved(true);
      setError('');
    } catch (problem) {
      setSaved(false);
      setError(problem.message);
    }
  }

  async function sweep(dryRun) {
    try {
      setReport(await clean({ dry_run: dryRun }));
      setError('');
    } catch (problem) {
      setError(problem.message);
    }
  }

  return (
    <div>
      {error && (
        <MessageBar intent="error" role="alert">
          <MessageBarBody>{error}</MessageBarBody>
        </MessageBar>
      )}
      <section className={styles.card} aria-label="Defaults">
        <Title3 as="h2">Default options</Title3>
        <Text>
          Downloads go to <code>{settings.download_dir}</code>. Options you leave empty in a new
          download use these. Logins and passwords are never saved.
        </Text>
        <Options
          forDefaults
          values={values}
          allowLocalPaths={settings.allow_local_paths}
          onChange={(id, next) => {
            setSaved(false);
            setValues((current) => ({ ...current, [id]: next }));
          }}
        />
        <div className={styles.row}>
          <Button appearance="primary" onClick={save}>
            Save defaults
          </Button>
        </div>
        {saved && (
          <MessageBar intent="success" role="status">
            <MessageBarBody>Saved to {settings.defaults_file}.</MessageBarBody>
          </MessageBar>
        )}
        <Text size={200}>RayoHX {settings.version}</Text>
      </section>

      <section className={styles.card} aria-label="Clean up">
        <Title3 as="h2">Clean up</Title3>
        <Body1>
          Interrupted downloads leave working folders behind. Removing one means that download
          starts again from the beginning. Running downloads are never touched.
        </Body1>
        <div className={styles.row}>
          <Button onClick={() => sweep(true)}>Preview</Button>
          <Button appearance="primary" onClick={() => sweep(false)}>
            Remove leftovers
          </Button>
        </div>
        {report && (
          <MessageBar intent="info" role="status">
            <MessageBarBody>
              {report.folders.length === 0
                ? 'Nothing to clean.'
                : `${report.dry_run ? 'Would remove' : 'Removed'} ${report.folders.length} folder(s), ${bytes(report.freed_bytes)}.`}
              {report.skipped_in_use > 0 && ` ${report.skipped_in_use} in use were skipped.`}
            </MessageBarBody>
          </MessageBar>
        )}
      </section>
    </div>
  );
}
