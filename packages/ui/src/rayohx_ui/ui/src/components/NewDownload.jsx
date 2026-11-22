import { useState } from 'react';
import {
  Body1,
  Button,
  Checkbox,
  Dropdown,
  Field,
  Input,
  MessageBar,
  MessageBarBody,
  Option,
  Spinner,
  Table,
  TableBody,
  TableCell,
  TableCellLayout,
  TableHeader,
  TableHeaderCell,
  TableRow,
  Title3,
  makeStyles,
  tokens,
} from '@fluentui/react-components';
import { ArrowDownload24Regular, Search24Regular } from '@fluentui/react-icons';
import { errorMessage, inspect, startDownload } from '../api.js';
import { bitrate } from '../format.js';

const useStyles = makeStyles({
  stack: { display: 'flex', flexDirection: 'column', rowGap: tokens.spacingVerticalL },
  row: { display: 'flex', columnGap: tokens.spacingHorizontalM, alignItems: 'flex-end' },
  grow: { flexGrow: 1 },
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
  fieldset: { border: 'none', padding: 0, margin: 0 },
  tracks: { display: 'flex', flexWrap: 'wrap', columnGap: tokens.spacingHorizontalXL },
});

/**
 * @typedef {object} Track
 * @property {string} group
 * @property {string} name
 * @property {string | null} [language]
 */
/**
 * @typedef {object} Variant
 * @property {number} index
 * @property {string | null} [name]
 * @property {string | null} [resolution]
 * @property {number | null} [bandwidth]
 * @property {string[]} codecs
 */
/**
 * @typedef {object} Playlist
 * @property {string} type
 * @property {Variant[]} [variants]
 * @property {Track[]} [audio_tracks]
 * @property {Track[]} [subtitle_tracks]
 * @property {number} [segments]
 * @property {number} [duration]
 */

const QUALITIES = ['best', '1080p', '720p', '480p', '360p', 'worst'];

/**
 * @param {{ onStarted: () => void, defaultQuality?: string }} props
 */
export default function NewDownload({ onStarted, defaultQuality = 'best' }) {
  const styles = useStyles();
  const [url, setUrl] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [playlist, setPlaylist] = useState(/** @type {Playlist | null} */ (null));
  const [quality, setQuality] = useState(defaultQuality);
  const [audio, setAudio] = useState(/** @type {string[]} */ ([]));
  const [subtitles, setSubtitles] = useState(/** @type {string[]} */ ([]));

  /** @param {import('react').FormEvent} event */
  async function look(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    setPlaylist(null);
    try {
      const data = await inspect(url.trim());
      setPlaylist(data.playlist);
      setAudio([]);
      setSubtitles([]);
    } catch (problem) {
      setError(errorMessage(problem));
    } finally {
      setBusy(false);
    }
  }

  async function start() {
    setBusy(true);
    setError('');
    try {
      await startDownload({ url: url.trim(), selection: { quality, audio, subtitles } });
      setPlaylist(null);
      setUrl('');
      onStarted();
    } catch (problem) {
      setError(errorMessage(problem));
    } finally {
      setBusy(false);
    }
  }

  /**
   * @param {string[]} list
   * @param {(next: string[]) => void} setList
   * @param {string} value
   */
  const toggle =
    (list, setList, value) =>
    (/** @type {unknown} */ _, /** @type {{ checked?: boolean | 'mixed' }} */ data) =>
      setList(data.checked ? [...list, value] : list.filter((item) => item !== value));
  /** @param {Track[]} [tracks] */
  const languages = (tracks = []) =>
    tracks.filter(
      /** @returns {t is Track & { language: string }} */
      (t) => Boolean(t.language),
    );

  return (
    <div className={styles.stack}>
      <form className={styles.card} onSubmit={look}>
        <Title3>Add a stream</Title3>
        <div className={styles.row}>
          <Field label="Playlist address" className={styles.grow}>
            <Input
              value={url}
              onChange={(_, data) => setUrl(data.value)}
              placeholder="https://cdn.example.com/vod/master.m3u8"
              type="url"
              required
            />
          </Field>
          <Button
            appearance="primary"
            type="submit"
            icon={busy ? <Spinner size="tiny" /> : <Search24Regular />}
            disabled={busy || !url.trim()}
          >
            Inspect
          </Button>
        </div>
        {error && (
          <MessageBar intent="error" role="alert">
            <MessageBarBody>{error}</MessageBarBody>
          </MessageBar>
        )}
      </form>

      {playlist && (
        <section className={styles.card} aria-label="Stream details">
          {playlist.type === 'master' ? (
            <>
              <Title3>{(playlist.variants ?? []).length} streams available</Title3>
              <Table size="small" aria-label="Available streams">
                <TableHeader>
                  <TableRow>
                    <TableHeaderCell>#</TableHeaderCell>
                    <TableHeaderCell>Resolution</TableHeaderCell>
                    <TableHeaderCell>Bitrate</TableHeaderCell>
                    <TableHeaderCell>Codecs</TableHeaderCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(playlist.variants ?? []).map((v) => (
                    <TableRow key={v.index}>
                      <TableCell>{v.index}</TableCell>
                      <TableCell>
                        <TableCellLayout>{v.resolution ?? v.name ?? '–'}</TableCellLayout>
                      </TableCell>
                      <TableCell>{bitrate(v.bandwidth)}</TableCell>
                      <TableCell>{v.codecs.join(', ') || '–'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <div className={styles.tracks}>
                {languages(playlist.audio_tracks).length > 0 && (
                  <fieldset className={styles.fieldset}>
                    <legend>Audio</legend>
                    {languages(playlist.audio_tracks).map((t) => (
                      <Checkbox
                        key={`${t.group}-${t.name}`}
                        label={`${t.name} (${t.language})`}
                        checked={audio.includes(t.language)}
                        onChange={toggle(audio, setAudio, t.language)}
                      />
                    ))}
                  </fieldset>
                )}
                {languages(playlist.subtitle_tracks).length > 0 && (
                  <fieldset className={styles.fieldset}>
                    <legend>Subtitles</legend>
                    {languages(playlist.subtitle_tracks).map((t) => (
                      <Checkbox
                        key={`${t.group}-${t.name}`}
                        label={`${t.name} (${t.language})`}
                        checked={subtitles.includes(t.language)}
                        onChange={toggle(subtitles, setSubtitles, t.language)}
                      />
                    ))}
                  </fieldset>
                )}
              </div>
            </>
          ) : (
            <Body1>
              Single stream: {playlist.segments} segments, {Math.round(playlist.duration ?? 0)} s.
            </Body1>
          )}
          <div className={styles.row}>
            <Field label="Quality">
              <Dropdown
                value={quality}
                selectedOptions={[quality]}
                onOptionSelect={(_, data) => setQuality(data.optionValue ?? quality)}
              >
                {QUALITIES.map((q) => (
                  <Option key={q} value={q}>
                    {q}
                  </Option>
                ))}
              </Dropdown>
            </Field>
            <Button
              appearance="primary"
              icon={<ArrowDownload24Regular />}
              onClick={start}
              disabled={busy}
            >
              Download
            </Button>
          </div>
        </section>
      )}
    </div>
  );
}
