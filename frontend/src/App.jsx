import { Routes, Route, NavLink } from 'react-router-dom'
import Dashboard from './pages/Dashboard.jsx'
import ModelInfo from './pages/ModelInfo.jsx'
import AlertsHistory from './pages/AlertsHistory.jsx'

const NAV = [
  { to: '/', label: 'Dashboard' },
  { to: '/model', label: 'Model' },
  { to: '/alerts', label: 'Alerts' },
]

export default function App() {
  return (
    <div className="min-h-screen bg-[#0a0f0a] text-[#e2e8e2] flex flex-col">
      <header className="border-b border-[#1e3a1e] bg-[#0d150d]">
        <div className="max-w-7xl mx-auto px-6 flex items-center gap-8 h-14">
          <div className="flex items-center gap-2">
            <span className="text-[#4ade80] text-lg">🔥</span>
            <span className="font-semibold tracking-wide text-[#e2e8e2]">ARGUS</span>
            <span className="text-xs text-[#6b8f6b] ml-1">Fire Risk Monitor</span>
          </div>
          <nav className="flex gap-1 ml-4">
            {NAV.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  `px-4 py-1.5 rounded text-sm transition-colors ${
                    isActive
                      ? 'bg-[#1a3a1a] text-[#4ade80] font-medium'
                      : 'text-[#8aab8a] hover:text-[#e2e8e2] hover:bg-[#121f12]'
                  }`
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-[#4ade80] animate-pulse" />
            <span className="text-xs text-[#6b8f6b]">Live</span>
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-7xl mx-auto w-full px-6 py-6">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/model" element={<ModelInfo />} />
          <Route path="/alerts" element={<AlertsHistory />} />
        </Routes>
      </main>
    </div>
  )
}
