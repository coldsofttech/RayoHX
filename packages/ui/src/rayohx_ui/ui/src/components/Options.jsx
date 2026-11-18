import {
  Accordion,
  AccordionHeader,
  AccordionItem,
  AccordionPanel,
  Checkbox,
  Dropdown,
  Field,
  Input,
  Option,
  Textarea,
  makeStyles,
  tokens,
} from '@fluentui/react-components';
import { SECTIONS } from '../options.js';

const useStyles = makeStyles({
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(15rem, 1fr))',
    gap: tokens.spacingHorizontalM,
  },
});

function Control({ field, value, onChange }) {
  switch (field.type) {
    case 'bool':
      return (
        <Checkbox
          label={field.label}
          checked={value ?? field.fallback ?? false}
          onChange={(_, data) => onChange(Boolean(data.checked))}
        />
      );
    case 'select':
      return (
        <Field label={field.label} hint={field.hint}>
          <Dropdown
            value={value ?? ''}
            selectedOptions={value ? [value] : []}
            placeholder="Default"
            clearable
            onOptionSelect={(_, data) => onChange(data.optionValue)}
          >
            {field.options.map((choice) => (
              <Option key={choice} value={choice}>
                {choice}
              </Option>
            ))}
          </Dropdown>
        </Field>
      );
    case 'lines':
      return (
        <Field label={field.label} hint={field.hint}>
          <Textarea value={value ?? ''} onChange={(_, data) => onChange(data.value)} rows={3} />
        </Field>
      );
    default:
      return (
        <Field label={field.label} hint={field.hint}>
          <Input
            value={value ?? ''}
            type={
              field.type === 'secret' ? 'password' : field.type === 'number' ? 'number' : 'text'
            }
            autoComplete="off"
            onChange={(_, data) => onChange(data.value)}
          />
        </Field>
      );
  }
}

/** Collapsible groups of every download option. Fields left empty use the defaults. */
export default function Options({ values, onChange, allowLocalPaths }) {
  const styles = useStyles();
  return (
    <Accordion collapsible multiple>
      {SECTIONS.map((section) => (
        <AccordionItem key={section.id} value={section.id}>
          <AccordionHeader>{section.title}</AccordionHeader>
          <AccordionPanel>
            <div className={styles.grid}>
              {section.fields
                .filter((field) => !field.local || allowLocalPaths)
                .map((field) => {
                  const id = `${section.id}.${field.key}`;
                  return (
                    <Control
                      key={id}
                      field={field}
                      value={values[id]}
                      onChange={(next) => onChange(id, next)}
                    />
                  );
                })}
            </div>
          </AccordionPanel>
        </AccordionItem>
      ))}
    </Accordion>
  );
}
