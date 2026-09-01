import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { AnalysisCacheProvider } from './analysisCache'
import { PlayerProvider } from './player'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AnalysisCacheProvider>
      <PlayerProvider>
        <App />
      </PlayerProvider>
    </AnalysisCacheProvider>
  </StrictMode>,
)
