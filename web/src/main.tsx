import '@fontsource-variable/fraunces'
import '@fontsource-variable/inter'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import './index.css'

// ?estatico=1 desactiva las apariciones con scroll: todo visible (capturas e impresión).
if (new URLSearchParams(window.location.search).has('estatico')) {
  document.documentElement.setAttribute('data-static', '')
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
