import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { SpikeHarness } from './spike/SpikeHarness';
import { createShell } from './shell/createShell';
import { replaceRuntime } from './transport/runtime';
import './styles/tailwind.css';
import './styles/shell.css';
import './styles/controls.css';

const root = document.getElementById('root');
if (!root) throw new Error('The frontend document is missing its root.');

/* The shell is built once, here, outside the tree, so StrictMode's second pass and a remount reuse the
   one runtime. A hot update re-runs this module: the runtime it replaces is disposed first, so two
   owners never hold a stream each. */
const shell = createShell();
replaceRuntime(shell.runtime);

createRoot(root).render(
  <StrictMode>
    <App shell={shell} />
    <SpikeHarness />
  </StrictMode>,
);
