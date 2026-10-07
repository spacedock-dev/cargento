import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MigrationShell } from './MigrationShell';

describe('a contributor opens the frontend preview', () => {
  it('explains that session views are unavailable without offering incomplete actions', () => {
    render(<MigrationShell />);

    expect(screen.getByRole('heading', { level: 1, name: 'Cargento frontend preview' })).toBeVisible();
    expect(screen.getByText(/session views are not available here yet/i)).toBeVisible();
    expect(screen.getByText(/use the Python dashboard/i)).toBeVisible();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});
