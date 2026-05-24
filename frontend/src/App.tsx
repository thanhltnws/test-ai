import { useState } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Navbar from './components/Navbar'
import Dashboard from './pages/Dashboard'
import Chat from './pages/Chat'
import Analysis from './pages/Analysis'
import Pipeline from './pages/Pipeline'
import WelcomeModal from './components/WelcomeModal'

export default function App() {
  const [welcomeOpen, setWelcomeOpen] = useState(() => {
    return !localStorage.getItem('welcome-seen')
  })

  return (
    <BrowserRouter>
      <WelcomeModal open={welcomeOpen} onClose={() => { localStorage.setItem('welcome-seen', '1'); setWelcomeOpen(false) }} />
      <Navbar onOpenWelcome={() => setWelcomeOpen(true)} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflowY: 'auto', minWidth: 0 }}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/analysis" element={<Analysis />} />
          <Route path="/ingestion" element={<Pipeline />} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}
