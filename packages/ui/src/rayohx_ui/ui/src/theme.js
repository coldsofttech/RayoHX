// RayoHX brand theme for Fluent UI: slate neutrals from the brand assets (dark #1e293b,
// light #f1f5f9, ink #334155, muted #94a3b8) with an orange accent, red for danger and yellow for
// warnings. Change a colour here and every component follows.
import { createDarkTheme, createLightTheme } from '@fluentui/react-components';

export const brand = {
  10: '#060200',
  20: '#261000',
  30: '#3f1800',
  40: '#561f00',
  50: '#6e2700',
  60: '#872f00',
  70: '#a03800',
  80: '#b94100',
  90: '#d34a00',
  100: '#ea580c',
  110: '#f06a22',
  120: '#f47e3d',
  130: '#f89259',
  140: '#fba477',
  150: '#fdb897',
  160: '#fecdb8',
};

export const slate = {
  ink: '#334155',
  night: '#1e293b',
  nightDeep: '#172033',
  nightRaised: '#26344a',
  mist: '#f1f5f9',
  muted: '#94a3b8',
};

export const lightTheme = {
  ...createLightTheme(brand),
  colorNeutralBackground1: '#ffffff',
  colorNeutralBackground2: slate.mist,
  colorNeutralBackground3: '#e2e8f0',
  colorNeutralForeground1: slate.night,
  colorNeutralForeground2: slate.ink,
  colorNeutralForeground3: '#64748b',
  colorNeutralStroke1: '#cbd5e1',
  colorNeutralStroke2: '#e2e8f0',
  colorStatusDangerBackground3: '#dc2626',
  colorStatusDangerForeground1: '#b91c1c',
  colorStatusWarningBackground3: '#eab308',
  colorStatusWarningForeground1: '#854d0e',
};

export const darkTheme = {
  ...createDarkTheme(brand),
  colorNeutralBackground1: slate.night,
  colorNeutralBackground2: slate.nightDeep,
  colorNeutralBackground3: slate.nightRaised,
  colorNeutralForeground1: slate.mist,
  colorNeutralForeground2: '#cbd5e1',
  colorNeutralForeground3: slate.muted,
  colorNeutralStroke1: '#475569',
  colorNeutralStroke2: '#334155',
  colorStatusDangerBackground3: '#ef4444',
  colorStatusDangerForeground1: '#f87171',
  colorStatusWarningBackground3: '#facc15',
  colorStatusWarningForeground1: '#fde047',
};
