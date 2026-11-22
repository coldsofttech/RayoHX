import { describe, expect, it } from 'vitest';

import {
  PROXY_SCHEMES,
  buildOptions,
  buildSource,
  convert,
  lookup,
  streamChoices,
} from './options';

describe('convert', () => {
  it('leaves untouched fields alone', () => {
    expect(convert({ type: 'text' }, undefined)).toBeUndefined();
    expect(convert({ type: 'number' }, '')).toBeUndefined();
  });

  it('scales numbers and drops ones that are not numbers', () => {
    expect(convert({ type: 'number', scale: 1000 }, '2.5')).toBe(2500);
    expect(convert({ type: 'number' }, 'abc')).toBeUndefined();
  });

  it('splits lists and pairs', () => {
    expect(convert({ type: 'list' }, ' a, b ,,c')).toEqual(['a', 'b', 'c']);
    expect(convert({ type: 'list' }, ' , ')).toBeUndefined();
    expect(convert({ type: 'lines', pairs: ':' }, 'A: 1\nbad\nB:2')).toEqual({ A: '1', B: '2' });
    expect(convert({ type: 'lines', pairs: ':' }, 'bad')).toBeUndefined();
  });

  it('only reports a choice that differs from its default', () => {
    expect(convert({ type: 'bool', fallback: true }, true)).toBeUndefined();
    expect(convert({ type: 'bool', fallback: true }, false)).toBe(false);
    expect(convert({ type: 'bool' }, true)).toBe(true);
    expect(convert({ type: 'bool' }, false)).toBeUndefined();
  });
});

describe('buildOptions', () => {
  it('groups set values by section and nests dotted keys', () => {
    const request = buildOptions({
      'network.retries': '5',
      'network.proxy.url': 'http://p:1',
      'network.headers': 'X-Token: abc',
      'selection.bandwidth': '2',
    });
    expect(request).toEqual({
      network: { retries: 5, proxy: { url: 'http://p:1' }, headers: { 'X-Token': 'abc' } },
      selection: { bandwidth: 2000 },
    });
  });

  it('leaves track names out when video only is ticked', () => {
    expect(
      buildOptions({ 'selection.audio_names': 'English', 'selection.video_only': true }),
    ).toEqual({ selection: { video_only: true } });
  });

  it('sends nothing when the form is untouched', () => {
    expect(buildOptions({})).toEqual({});
  });
});

describe('buildSource', () => {
  const input = {
    url: ' https://x/a.m3u8 ',
    urls: 'https://a\n\n# skip\n https://b ',
    text: '#EXTM3U',
    base: ' https://x/ ',
  };

  it('builds each source mode', () => {
    expect(buildSource('url', input)).toEqual({ url: 'https://x/a.m3u8' });
    expect(buildSource('many', input)).toEqual({ urls: ['https://a', 'https://b'] });
    expect(buildSource('text', input)).toEqual({
      playlist_text: '#EXTM3U',
      base_url: 'https://x/',
    });
  });
});

describe('streamChoices', () => {
  it('lists only what the stream offers', () => {
    const choices = streamChoices({
      variants: [
        { index: 1, name: 'HD', resolution: '1920x1080', bandwidth: 4000000 },
        { index: 2, name: null, resolution: '1280x720', bandwidth: 2000000 },
      ],
      audio_tracks: [{ name: 'English' }],
    });
    expect(choices['selection.max_resolution'].map((c) => c.value)).toEqual(['1080p', '720p']);
    expect(choices['selection.bandwidth'].map((c) => c.value)).toEqual(['4000', '2000']);
    expect(choices['selection.variant'][0].label).toBe('#1 · 1920x1080 · 4000 kbps');
    expect(choices['selection.audio_names']).toEqual([{ value: 'English', label: 'English' }]);
    expect(choices).not.toHaveProperty('selection.subtitle_names');
  });

  it('lists sizes from largest to smallest', () => {
    const choices = streamChoices({
      variants: ['320x184', '1920x1080', '848x480', '1280x720'].map((resolution, i) => ({
        index: i,
        resolution,
      })),
    });
    expect(choices['selection.resolution'].map((c) => c.value)).toEqual([
      '1920x1080',
      '1280x720',
      '848x480',
      '320x184',
    ]);
  });
});

describe('PROXY_SCHEMES', () => {
  it('lists the address schemes a proxy can use', () => {
    expect(PROXY_SCHEMES).toEqual(['http', 'https', 'socks5', 'socks5h']);
  });
});

describe('lookup', () => {
  it('reads the entry stored under an id', () => {
    expect(lookup({ 'network.retries': '5' }, 'network.retries')).toBe('5');
    expect(lookup({ 'network.insecure': false }, 'network.insecure')).toBe(false);
  });

  it('gives undefined for an id that is not there, or no record at all', () => {
    expect(lookup({}, 'network.retries')).toBeUndefined();
    expect(lookup(undefined, 'network.retries')).toBeUndefined();
  });

  it('never reaches the prototype of the record', () => {
    expect(lookup({}, 'constructor')).toBeUndefined();
    expect(lookup({}, '__proto__')).toBeUndefined();
    expect(lookup({}, 'toString')).toBeUndefined();
  });
});
