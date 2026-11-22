import {
  Accordion,
  AccordionHeader,
  AccordionItem,
  AccordionPanel,
} from '@fluentui/react-components';
import { SECTIONS } from '../../../options.js';
import Fields from './Fields.jsx';

/**
 * Collapsible groups of every download option. Fields left empty use the defaults.
 * Sections in `hidden` are left out. `choices` maps a field id to the values the inspected stream
 * offers, which turns that field into a dropdown; its section then starts open.
 * @param {{ values: Record<string, any>, onChange: (id: string, next: any) => void, allowLocalPaths?: boolean, hidden?: string[], choices?: Record<string, { value: string, label: string }[]> }} props
 */
export default function Options({
  values,
  onChange,
  allowLocalPaths = false,
  hidden = [],
  choices,
}) {
  return (
    <Accordion collapsible multiple defaultOpenItems={choices ? ['selection'] : []}>
      {SECTIONS.filter((section) => !hidden.includes(section.id)).map((section) => (
        <AccordionItem key={section.id} value={section.id}>
          <AccordionHeader>{section.title}</AccordionHeader>
          <AccordionPanel>
            <Fields
              fields={section.fields.filter((field) => !field.local || allowLocalPaths)}
              prefix={section.id}
              values={values}
              onChange={onChange}
              choices={choices}
            />
          </AccordionPanel>
        </AccordionItem>
      ))}
    </Accordion>
  );
}
