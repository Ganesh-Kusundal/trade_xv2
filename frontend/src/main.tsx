/**
 * Entry point. Mounts <App /> in StrictMode.
 */

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import './styles/globals.css'

const el = document.getElementById('root')!
createRoot(el).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
