import { lookup } from '../../../options.js';
import Control from './Control.jsx';
import { useOptionStyles } from './styles.js';

/** Fields in an aligned grid; tick boxes take a full row so they never push the inputs around. */
export default function Grid({ fields, prefix, values, onChange, choices }) {
  const styles = useOptionStyles();
  return (
    <div className={styles.grid}>
      {fields.map((field) => {
        const id = `${prefix}.${field.key}`;
        const control = (
          <Control
            key={id}
            field={field}
            value={lookup(values, id)}
            onChange={(next) => onChange(id, next)}
            choices={lookup(choices, id)}
          />
        );
        return field.type === 'bool' || field.type === 'lines' ? (
          <div key={id} className={field.type === 'bool' ? styles.wide : undefined}>
            {control}
          </div>
        ) : (
          control
        );
      })}
    </div>
  );
}
