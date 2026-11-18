import { useEffect, useState } from 'react';
import {
  Body1,
  Button,
  Dropdown,
  Field,
  MessageBar,
  MessageBarBody,
  Option,
  Slider,
  Switch,
  Text,
  Title3,
  makeStyles,
  tokens,
} from '@fluentui/react-components';
import { clean, getSettings, saveSettings } from '../api.js';
import { bytes } from '../format.js';

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

const QUALITIES = ['best', '1080p', '720p', '480p', '360p', 'worst'];

export default function Settings({ onChanged }) {
  const styles = useStyles();
  const [settings, setSettings] = useState(null);
  const [report, setReport] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    getSettings().then(setSettings, (problem) => setError(problem.message));
  }, []);

  async function change(changes) {
    try {
      const next = await saveSettings(changes);
      setSettings(next);
      onChanged?.(next);
    } catch (problem) {
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

  if (!settings) {
    return error ? (
      <MessageBar intent="error" role="alert">
        <MessageBarBody>{error}</MessageBarBody>
      </MessageBar>
    ) : null;
  }

  return (
    <div>
      {error && (
        <MessageBar intent="error" role="alert">
          <MessageBarBody>{error}</MessageBarBody>
        </MessageBar>
      )}
      <section className={styles.card} aria-label="Defaults">
        <Title3 as="h2">Defaults</Title3>
        <Text>
          Saved in: <code>{settings.download_dir}</code>
        </Text>
        <Field label={`Parallel segments: ${settings.concurrency}`}>
          <Slider
            min={1}
            max={16}
            value={settings.concurrency}
            onChange={(_, data) => change({ concurrency: data.value })}
          />
        </Field>
        <Field label="Default quality">
          <Dropdown
            value={settings.quality}
            selectedOptions={[settings.quality]}
            onOptionSelect={(_, data) => change({ quality: data.optionValue })}
          >
            {QUALITIES.map((q) => (
              <Option key={q} value={q}>
                {q}
              </Option>
            ))}
          </Dropdown>
        </Field>
        <Switch
          label="Replace files that already exist"
          checked={settings.overwrite}
          onChange={(_, data) => change({ overwrite: data.checked })}
        />
        <Text size={200}>These apply until the app is closed. Version {settings.version}.</Text>
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
