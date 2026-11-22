import { Dropdown, Field, Option } from '@fluentui/react-components';

const QUALITIES = ['best', '1080p', '720p', '480p', '360p', 'worst'];

/** @param {{ value: string, onChange: (quality: string) => void }} props */
export default function Quality({ value, onChange }) {
  return (
    <Field label="Quality">
      <Dropdown
        value={value}
        selectedOptions={[value]}
        onOptionSelect={(_, data) => onChange(data.optionValue ?? value)}
      >
        {QUALITIES.map((q) => (
          <Option key={q} value={q}>
            {q}
          </Option>
        ))}
      </Dropdown>
    </Field>
  );
}
