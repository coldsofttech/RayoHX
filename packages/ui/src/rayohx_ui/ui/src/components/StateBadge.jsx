import { Badge } from '@fluentui/react-components';

const BADGE = {
  downloading: { color: 'brand', appearance: 'filled' },
  verifying: { color: 'brand', appearance: 'tint' },
  paused: { color: 'warning', appearance: 'filled' },
  failed: { color: 'danger', appearance: 'filled' },
  cancelled: { color: 'danger', appearance: 'outline' },
  completed: { color: 'success', appearance: 'filled' },
};

export default function StateBadge({ state }) {
  const style = BADGE[state] ?? { color: 'informative', appearance: 'tint' };
  return <Badge {...style}>{state}</Badge>;
}
