import { useEffect, useState } from 'react';
import {
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
} from '@fluentui/react-components';
import { bridge, errorMessage, settings as settingsApi } from '../../api/index.js';
import About from './About.jsx';
import CleanUp from './CleanUp.jsx';
import { useCardStyles } from './styles.js';

/**
 * @typedef {object} Limits
 * @property {number} min_concurrency
 * @property {number} max_concurrency
 */
/**
 * @typedef {object} AppSettings
 * @property {string} download_dir
 * @property {number} concurrency
 * @property {string} quality
 * @property {boolean} overwrite
 * @property {Limits} limits
 * @property {string} version
 */

const QUALITIES = ['best', '1080p', '720p', '480p', '360p', 'worst'];

/** @param {{ onChanged?: (settings: AppSettings) => void }} props */
export default function Settings({ onChanged }) {
  const styles = useCardStyles();
  const [settings, setSettings] = useState(/** @type {AppSettings | null} */ (null));
  const [error, setError] = useState('');

  useEffect(() => {
    settingsApi.get().then(setSettings, (problem) => setError(errorMessage(problem)));
  }, []);

  /** @param {Record<string, unknown>} changes */
  async function change(changes) {
    try {
      const next = await settingsApi.save(changes);
      setSettings(next);
      onChanged?.(next);
    } catch (problem) {
      setError(errorMessage(problem));
    }
  }

  async function pickFolder() {
    try {
      const folder = await bridge.chooseFolder(settings?.download_dir);
      if (folder) await change({ download_dir: folder });
    } catch (problem) {
      setError(errorMessage(problem));
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
      <section className={styles.card} aria-label="Settings">
        <Title3 as="h2" className={styles.heading}>
          Settings
        </Title3>
        <div className={styles.split}>
          <Text>
            Saved in: <code>{settings.download_dir}</code>
          </Text>
          <Button onClick={pickFolder}>Change</Button>
        </div>
        <Field label={`Parallel segments: ${settings.concurrency}`}>
          <Slider
            min={settings.limits.min_concurrency}
            max={settings.limits.max_concurrency}
            value={settings.concurrency}
            onChange={(_, data) => change({ concurrency: data.value })}
          />
        </Field>
        <Field label="Default quality">
          <Dropdown
            value={settings.quality}
            selectedOptions={[settings.quality]}
            onOptionSelect={(_, data) => data.optionValue && change({ quality: data.optionValue })}
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
        <Text size={200}>Your choices are remembered. New downloads use this folder.</Text>
      </section>

      <CleanUp />
      <About version={settings.version} />
    </div>
  );
}
