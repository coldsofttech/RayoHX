import { useEffect, useState } from 'react';
import {
  Body1,
  Button,
  Caption1,
  MessageBar,
  MessageBarBody,
  Text,
} from '@fluentui/react-components';
import { explainJob, jobEvents, makeReport, queueJob, queueVerification } from '../api.js';

function Section({ title, children }) {
  return (
    <section aria-label={title} style={{ marginTop: '0.5rem' }}>
      <Text weight="semibold" as="h3" block>
        {title}
      </Text>
      {children}
    </section>
  );
}

export default function JobDetails({ job }) {
  const [attempts, setAttempts] = useState(null);
  const [verification, setVerification] = useState(null);
  const [diagnosis, setDiagnosis] = useState(null);
  const [events, setEvents] = useState(null);
  const [report, setReport] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
    const keep = (set) => (value) => alive && set(value);
    queueJob(job.id).then(
      keep((d) => setAttempts(d.attempt_history)),
      () => {},
    );
    jobEvents(job.id).then(
      keep((d) => setEvents(d.items)),
      () => {},
    );
    if (job.verification && job.verification !== 'not_requested') {
      queueVerification(job.id).then(keep(setVerification), () => {});
    }
    if (job.state === 'failed') explainJob(job.id).then(keep(setDiagnosis), () => {});
    return () => {
      alive = false;
    };
  }, [job.id, job.state, job.verification]);

  async function save() {
    try {
      const saved = await makeReport(job.id);
      setReport(saved.path ?? '');
      setError('');
    } catch (problem) {
      setError(problem.message);
    }
  }

  const why = diagnosis?.explanation;
  return (
    <div>
      {why && (
        <Section title="What went wrong">
          <Body1 as="p">
            <strong>{why.title}.</strong> {why.what_happened} {why.likely_cause}
          </Body1>
          {why.what_was_tried && <Caption1 as="p">{why.what_was_tried}</Caption1>}
          <ul>
            {why.next_steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ul>
        </Section>
      )}
      {verification && (
        <Section title="Verification">
          <Body1 as="p">
            {verification.status} ({verification.level}), {verification.segments_checked} segments
          </Body1>
          <ul>
            {verification.checks.map((check) => (
              <li key={check.name}>
                {check.name}: {check.status}
                {check.detail && ` (${check.detail})`}
              </li>
            ))}
          </ul>
          {verification.notes.map((note) => (
            <Caption1 key={note} as="p">
              {note}
            </Caption1>
          ))}
        </Section>
      )}
      {attempts?.length > 0 && (
        <Section title="Runs">
          <ol>
            {attempts.map((a) => (
              <li key={a.attempt}>
                Run {a.attempt}: {a.outcome ?? 'running'}
                {a.error_code && ` (${a.error_code})`}
              </li>
            ))}
          </ol>
        </Section>
      )}
      {events?.length > 0 && (
        <Section title="Events">
          <ol aria-label="Job events" style={{ margin: 0, paddingLeft: '1.25rem' }}>
            {events.slice(-20).map((e) => (
              <li key={e.id}>
                <code>{new Date(e.timestamp * 1000).toLocaleTimeString()}</code> {e.type}
              </li>
            ))}
          </ol>
        </Section>
      )}
      <Button size="small" onClick={save}>
        Save a report to share
      </Button>
      {report && (
        <MessageBar intent="success">
          <MessageBarBody>
            Saved as {report}. Secrets and personal paths are removed.
          </MessageBarBody>
        </MessageBar>
      )}
      {error && (
        <MessageBar intent="error" role="alert">
          <MessageBarBody>{error}</MessageBarBody>
        </MessageBar>
      )}
    </div>
  );
}
