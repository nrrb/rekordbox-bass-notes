import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { AnalysisCacheProvider } from './analysisCache'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AnalysisCacheProvider>
      <App />
    </AnalysisCacheProvider>
  </StrictMode>,
)
