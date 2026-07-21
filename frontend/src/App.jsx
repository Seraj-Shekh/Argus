import { useState, useEffect, useCallback } from 'react'
import { Routes, Route, NavLink } from 'react-router-dom'
import Dashboard from './pages/Dashboard.jsx'
import ModelInfo from './pages/ModelInfo.jsx'
import AlertsHistory from './pages/AlertsHistory.jsx'

const REGION_CENTERS = {
  'Uusimaa':            { lat: 60.25, lon: 25.00 },
  'Varsinais-Suomi':    { lat: 60.50, lon: 22.30 },
  'Satakunta':          { lat: 61.50, lon: 22.00 },
  'Kanta-Häme':         { lat: 60.90, lon: 24.40 },
  'Pirkanmaa':          { lat: 61.70, lon: 23.80 },
  'Päijät-Häme':        { lat: 61.00, lon: 25.70 },
  'Kymenlaakso':        { lat: 60.70, lon: 26.70 },
  'Etelä-Karjala':      { lat: 61.10, lon: 28.20 },
  'Etelä-Savo':         { lat: 61.80, lon: 27.50 },
  'Pohjois-Savo':       { lat: 63.10, lon: 27.40 },
  'Pohjois-Karjala':    { lat: 62.60, lon: 29.80 },
  'Keski-Suomi':        { lat: 62.20, lon: 25.70 },
  'Etelä-Pohjanmaa':    { lat: 62.80, lon: 22.80 },
  'Pohjanmaa':          { lat: 63.10, lon: 21.70 },
  'Keski-Pohjanmaa':    { lat: 63.80, lon: 24.50 },
  'Pohjois-Pohjanmaa':  { lat: 65.00, lon: 26.50 },
  'Kainuu':             { lat: 64.30, lon: 28.50 },
  'Lappi':              { lat: 67.90, lon: 26.70 },
  'Ahvenanmaa':         { lat: 60.10, lon: 20.00 },
}

async function fetchRisk(name) {
  const center = REGION_CENTERS[name]
  if (!center) return null
  try {
    const res = await fetch('/api/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ station_lat: center.lat, station_lon: center.lon, location_name: name }),
    })
    if (!res.ok) return null
    return { name, ...(await res.json()) }
  } catch {
    return null
  }
}

const NAV = [
  { to: '/', label: 'Dashboard' },
  { to: '/model', label: 'Model' },
  { to: '/alerts', label: 'Alerts' },
]

export default function App() {
  // Dashboard data — lives here so it survives page navigation
  const [geojson, setGeojson]         = useState(null)
  const [riskMap, setRiskMap]         = useState({})
  const [geojsonKey, setGeojsonKey]   = useState(0)
  const [loading, setLoading]         = useState(true)
  const [backendDown, setBackendDown] = useState(false)
  const [lastUpdated, setLastUpdated] = useState(null)
  const [sensorNodes, setSensorNodes] = useState([])

  // Alerts data
  const [alerts, setAlerts]           = useState([])
  const [alertsLoading, setAlertsLoading] = useState(true)
  const [alertsError, setAlertsError] = useState(null)

  useEffect(() => {
    fetch('/finland-regions.geojson')
      .then((r) => r.json())
      .then(setGeojson)
      .catch(() => console.error('Could not load finland-regions.geojson'))
  }, [])

  useEffect(() => {
    fetch('/api/sensor-nodes')
      .then((r) => r.ok ? r.json() : [])
      .then(setSensorNodes)
      .catch(() => {})
  }, [])

  useEffect(() => {
    fetch('/api/alerts')
      .then((r) => {
        if (!r.ok) throw new Error(`Server returned ${r.status}`)
        return r.json()
      })
      .then((data) => { setAlerts(Array.isArray(data) ? data : []); setAlertsLoading(false) })
      .catch((e) => { setAlertsError(e.message); setAlertsLoading(false) })
  }, [])

  const loadRisk = useCallback(async () => {
    setLoading(true)
    setBackendDown(false)
    const names = Object.keys(REGION_CENTERS)
    const results = await Promise.all(names.map(fetchRisk))
    const ok = results.filter(Boolean)
    if (ok.length === 0) {
      setBackendDown(true)
    } else {
      const map = {}
      ok.forEach((r) => { map[r.name] = r })
      setRiskMap(map)
      setGeojsonKey((k) => k + 1)
      setLastUpdated(new Date())
    }
    setLoading(false)
  }, [])

  useEffect(() => { loadRisk() }, [loadRisk])

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
          <Route path="/" element={
            <Dashboard
              geojson={geojson}
              riskMap={riskMap}
              geojsonKey={geojsonKey}
              loading={loading}
              backendDown={backendDown}
              lastUpdated={lastUpdated}
              sensorNodes={sensorNodes}
              setSensorNodes={setSensorNodes}
              loadRisk={loadRisk}
            />
          } />
          <Route path="/model" element={<ModelInfo />} />
          <Route path="/alerts" element={
            <AlertsHistory
              alerts={alerts}
              loading={alertsLoading}
              error={alertsError}
            />
          } />
        </Routes>
      </main>
    </div>
  )
}
