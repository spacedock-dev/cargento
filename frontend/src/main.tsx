import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { MigrationShell } from './MigrationShell';
import './styles.css';

const root = document.getElementById('root');
if (!root) throw new Error('The frontend document is missing its root.');

createRoot(root).render(
  <StrictMode>
    <MigrationShell />
  </StrictMode>,
);
