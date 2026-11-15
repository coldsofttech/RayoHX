import { describe, expect, it } from 'vitest';
import { axe } from 'vitest-axe';
import { render, screen } from '@testing-library/react';
import App from './App.jsx';

describe('App', () => {
  it('shows the placeholder page', () => {
    render(<App />);
    expect(screen.getByRole('heading', { name: 'RayoHX' })).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<App />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
