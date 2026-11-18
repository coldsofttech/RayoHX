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
  Tab,
  TabList,
  Textarea,
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
import { inspect, startDownload } from '../api.js';
import { bitrate } from '../format.js';
import { buildOptions, buildSource } from '../options.js';
import Options from './Options.jsx';

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

const QUALITIES = ['best', '1080p', '720p', '480p', '360p', 'worst'];

export default function NewDownload({
  onStarted,
  defaultQuality = 'best',
  allowLocalPaths = false,
}) {
  const styles = useStyles();
  const [mode, setMode] = useState('url');
  const [url, setUrl] = useState('');
  const [urls, setUrls] = useState('');
  const [text, setText] = useState('');
  const [base, setBase] = useState('');
  const [filename, setFilename] = useState('');
  const [values, setValues] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [playlist, setPlaylist] = useState(null);
  const [quality, setQuality] = useState(defaultQuality);
  const [audio, setAudio] = useState([]);
  const [subtitles, setSubtitles] = useState([]);

  const input = { url, urls, text, base };
  const source = buildSource(mode, input);
  const ready =
    mode === 'url' ? url.trim() : mode === 'many' ? urls.trim() : text.trim() && base.trim();
  const setValue = (id, next) => setValues((current) => ({ ...current, [id]: next }));

  // Inspect looks at the first address only; a batch is inspected through its first stream.
  const inspectSource = mode === 'many' ? { url: source.urls[0] } : source;

  async function look(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    setPlaylist(null);
    try {
      const { network } = buildOptions(values);
      const data = await inspect({ ...inspectSource, network });
      setPlaylist(data.playlist);
      setAudio([]);
      setSubtitles([]);
    } catch (problem) {
      setError(problem.message);
    } finally {
      setBusy(false);
    }
  }

  async function start() {
    setBusy(true);
    setError('');
    try {
      const options = buildOptions(values);
      await startDownload({
        ...source,
        ...(filename.trim() && mode !== 'many' ? { filename: filename.trim() } : {}),
        ...options,
        selection: { ...options.selection, quality, audio, subtitles },
      });
      setPlaylist(null);
      setUrl('');
      setUrls('');
      setText('');
      onStarted();
    } catch (problem) {
      setError(problem.message);
    } finally {
      setBusy(false);
    }
  }

  const toggle = (list, setList, value) => (_, data) =>
    setList(data.checked ? [...list, value] : list.filter((item) => item !== value));
  const languages = (tracks) => tracks.filter((t) => t.language);

  return (
    <div className={styles.stack}>
      <form className={styles.card} onSubmit={look}>
        <Title3>Add a stream</Title3>
        <TabList size="small" selectedValue={mode} onTabSelect={(_, d) => setMode(d.value)}>
          <Tab value="url">One address</Tab>
          <Tab value="many">Several addresses</Tab>
          <Tab value="text">Playlist text</Tab>
        </TabList>
        {mode === 'url' && (
          <Field label="Playlist address">
            <Input
              value={url}
              onChange={(_, data) => setUrl(data.value)}
              placeholder="https://cdn.example.com/vod/master.m3u8"
              type="url"
              required
            />
          </Field>
        )}
        {mode === 'many' && (
          <Field label="Playlist addresses" hint="One per line. Lines starting with # are ignored.">
            <Textarea value={urls} onChange={(_, data) => setUrls(data.value)} rows={4} />
          </Field>
        )}
        {mode === 'text' && (
          <>
            <Field label="Playlist text" hint="The contents of an .m3u8 file you already have.">
              <Textarea value={text} onChange={(_, data) => setText(data.value)} rows={5} />
            </Field>
            <Field
              label="Base address"
              hint="Relative addresses in the playlist are resolved against it."
            >
              <Input value={base} onChange={(_, data) => setBase(data.value)} type="url" />
            </Field>
          </>
        )}
        {mode !== 'many' && (
          <Field label="File name" hint="Optional. Saved in the download folder.">
            <Input value={filename} onChange={(_, data) => setFilename(data.value)} />
          </Field>
        )}
        <Options values={values} onChange={setValue} allowLocalPaths={allowLocalPaths} />
        <div className={styles.row}>
          <Button
            appearance="primary"
            type="submit"
            icon={busy ? <Spinner size="tiny" /> : <Search24Regular />}
            disabled={busy || !ready}
          >
            Inspect
          </Button>
          {mode === 'many' && (
            <Button icon={<ArrowDownload24Regular />} onClick={start} disabled={busy || !ready}>
              Download all
            </Button>
          )}
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
              <Title3>{playlist.variants.length} streams available</Title3>
              <Table size="small" aria-label="Available streams">
                <TableHeader>
                  <TableRow>
                    <TableHeaderCell>#</TableHeaderCell>
                    <TableHeaderCell>Resolution</TableHeaderCell>
                    <TableHeaderCell>Bitrate</TableHeaderCell>
                    <TableHeaderCell>Codecs</TableHeaderCell>
                    <TableHeaderCell>Use</TableHeaderCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {playlist.variants.map((v) => (
                    <TableRow key={v.index}>
                      <TableCell>{v.index}</TableCell>
                      <TableCell>
                        <TableCellLayout>{v.resolution ?? v.name ?? '–'}</TableCellLayout>
                      </TableCell>
                      <TableCell>{bitrate(v.bandwidth)}</TableCell>
                      <TableCell>{v.codecs.join(', ') || '–'}</TableCell>
                      <TableCell>
                        <Button
                          size="small"
                          appearance={
                            values['selection.variant'] === String(v.index) ? 'primary' : 'outline'
                          }
                          aria-label={`Use stream ${v.index}`}
                          onClick={() =>
                            setValue(
                              'selection.variant',
                              values['selection.variant'] === String(v.index)
                                ? ''
                                : String(v.index),
                            )
                          }
                        >
                          {values['selection.variant'] === String(v.index) ? 'Chosen' : 'Choose'}
                        </Button>
                      </TableCell>
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
              Single stream: {playlist.segments} segments, {Math.round(playlist.duration)} s.
            </Body1>
          )}
          <div className={styles.row}>
            <Field label="Quality">
              <Dropdown
                value={quality}
                selectedOptions={[quality]}
                onOptionSelect={(_, data) => setQuality(data.optionValue)}
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
