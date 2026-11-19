import { useEffect, useState } from 'react';
import {
  Badge,
  Button,
  FluentProvider,
  Tab,
  TabList,
  Title2,
  makeStyles,
  tokens,
} from '@fluentui/react-components';
import { WeatherMoon24Regular, WeatherSunny24Regular } from '@fluentui/react-icons';
import { darkTheme, lightTheme } from './theme.js';
import { getSettings } from './api.js';
import { toValues } from './options.js';
import NewDownload from './components/NewDownload.jsx';
import Queue from './components/Queue.jsx';
import Storage from './components/Storage.jsx';
import Settings from './components/Settings.jsx';

const useStyles = makeStyles({
  shell: {
    minHeight: '100vh',
    backgroundColor: tokens.colorNeutralBackground2,
    color: tokens.colorNeutralForeground1,
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: `${tokens.spacingVerticalM} ${tokens.spacingHorizontalXL}`,
    backgroundColor: tokens.colorNeutralBackground1,
    borderBottom: `2px solid ${tokens.colorBrandBackground}`,
  },
  main: { maxWidth: '60rem', margin: '0 auto', padding: tokens.spacingHorizontalXL },
  tabs: { marginBottom: tokens.spacingVerticalL },
});

function initialDark() {
  try {
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false;
  } catch {
    return false;
  }
}

export default function App() {
  const styles = useStyles();
  const [dark, setDark] = useState(initialDark);
  const [tab, setTab] = useState('new');
  const [active, setActive] = useState(0);
  const [settings, setSettings] = useState(null);

  useEffect(() => {
    getSettings().then(setSettings, () => {});
  }, []);

  return (
    <FluentProvider theme={dark ? darkTheme : lightTheme}>
      <div className={styles.shell}>
        <header className={styles.header}>
          <Title2 as="h1">RayoHX</Title2>
          <Button
            appearance="subtle"
            icon={dark ? <WeatherSunny24Regular /> : <WeatherMoon24Regular />}
            onClick={() => setDark(!dark)}
            aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}
          />
        </header>
        <main className={styles.main}>
          <TabList
            className={styles.tabs}
            selectedValue={tab}
            onTabSelect={(_, data) => setTab(data.value)}
          >
            <Tab value="new">New</Tab>
            <Tab value="queue">
              Queue{' '}
              {active > 0 && (
                <Badge appearance="filled" color="brand" size="small">
                  {active}
                </Badge>
              )}
            </Tab>
            <Tab value="storage">Storage</Tab>
            <Tab value="settings">Settings</Tab>
          </TabList>
          {tab === 'new' && (
            <NewDownload
              inherited={toValues(settings?.defaults)}
              allowLocalPaths={settings?.allow_local_paths ?? false}
              onStarted={() => setTab('queue')}
            />
          )}
          {tab === 'queue' && <Queue onCount={setActive} />}
          {tab === 'storage' && <Storage />}
          {tab === 'settings' && settings && (
            <Settings settings={settings} onChanged={setSettings} />
          )}
        </main>
      </div>
    </FluentProvider>
  );
}
