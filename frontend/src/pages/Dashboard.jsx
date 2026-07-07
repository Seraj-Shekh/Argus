import { useState, useEffect, useCallback } from 'react'
import { MapContainer, TileLayer, GeoJSON } from 'react-leaflet'

const FINLAND_CENTER = [65.0, 26.0]
const FINLAND_BOUNDS = [[59.3, 19.0], [70.1, 31.6]]

// Center coordinate used to call /api/predict for each region
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

const RISK_FILL = {
  high:    { fill: '#ef4444', opacity: 0.65 },
  medium:  { fill: '#fb923c', opacity: 0.50 },
  low:     { fill: '#4ade80', opacity: 0.30 },
  unknown: { fill: '#374151', opacity: 0.20 },
}

function riskStyle(riskLevel) {
  const { fill, opacity } = RISK_FILL[riskLevel] ?? RISK_FILL.unknown
  return {
    fillColor: fill,
    fillOpacity: opacity,
    color: '#0a0f0a',
    weight: 1.5,
  }
}

function RiskBadge({ level }) {
  const s = {
    low:    'bg-green-900/50 text-green-400 border-green-700',
    medium: 'bg-orange-900/50 text-orange-400 border-orange-700',
    high:   'bg-red-900/50 text-red-400 border-red-700',
  }
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold border ${s[level] ?? s.low}`}>
      {level?.toUpperCase()}
    </span>
  )
}

function Row({ label, value }) {
  return (
    <div className="flex justify-between gap-4 py-0.5">
      <span className="text-[#6b8f6b]">{label}</span>
      <span className="text-[#c8dcc8] text-right">{value ?? '—'}</span>
    </div>
  )
}

async function fetchRisk(name) {
  const center = REGION_CENTERS[name]
  if (!center) return null
  try {
    const res = await fetch('/api/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ station_lat: center.lat, station_lon: center.lon }),
    })
    if (!res.ok) return null
    return { name, ...(await res.json()) }
  } catch {
    return null
  }
}

export default function Dashboard() {
  const [geojson, setGeojson]       = useState(null)
  const [riskMap, setRiskMap]       = useState({})   // { regionName: predictionResult }
  const [geojsonKey, setGeojsonKey] = useState(0)    // forces GeoJSON re-render on data load
  const [loading, setLoading]       = useState(true)
  const [backendDown, setBackendDown] = useState(false)
  const [selected, setSelected]     = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)

  // Load GeoJSON boundaries once
  useEffect(() => {
    fetch('/finland-regions.geojson')
      .then((r) => r.json())
      .then(setGeojson)
      .catch(() => console.error('Could not load finland-regions.geojson'))
  }, [])

  // Fetch predictions for all regions
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
      setGeojsonKey((k) => k + 1)   // trigger GeoJSON re-render with new colours
      setLastUpdated(new Date())
    }
    setLoading(false)
  }, [])

  useEffect(() => { loadRisk() }, [loadRisk])

  // GeoJSON layer style — called per feature
  const styleFeature = useCallback(
    (feature) => riskStyle(riskMap[feature.properties.nimi]?.risk_level),
    [riskMap],
  )

  // Attach hover + click to each region polygon
  const onEachFeature = useCallback(
    (feature, layer) => {
      const name = feature.properties.nimi
      layer.on({
        mouseover(e) {
          e.target.setStyle({ weight: 3, color: '#ffffff', fillOpacity: 0.8 })
        },
        mouseout(e) {
          e.target.setStyle(riskStyle(riskMap[name]?.risk_level))
        },
        click() {
          setSelected(riskMap[name] ? { name, ...riskMap[name] } : { name })
        },
      })
      const risk = riskMap[name]
      layer.bindTooltip(
        `<strong>${name}</strong>${risk ? `<br/>${risk.risk_level?.toUpperCase()} · ${(risk.fire_risk * 100).toFixed(0)}%` : ''}`,
        { sticky: true, className: 'argus-tooltip' },
      )
    },
    [riskMap],
  )

  const regions = Object.values(riskMap)
  const highCount = regions.filter((r) => r.risk_level === 'high').length
  const medCount  = regions.filter((r) => r.risk_level === 'medium').length
  const avgRisk   = regions.length
    ? (regions.reduce((s, r) => s + r.fire_risk, 0) / regions.length * 100).toFixed(1)
    : null

  return (
    <div className="flex flex-col gap-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-[#e2e8e2]">Fire Risk Map — Finland</h1>
          <p className="text-sm text-[#6b8f6b] mt-0.5">
            19 regions · live FMI weather · predictions load on open
          </p>
        </div>
        <div className="flex items-center gap-3">
          {loading && <span className="text-xs text-[#4ade80] animate-pulse">Fetching FMI data…</span>}
          {!loading && !backendDown && lastUpdated && (
            <span className="text-xs text-[#6b8f6b]">Updated {lastUpdated.toLocaleTimeString('fi-FI')}</span>
          )}
          <button
            onClick={loadRisk}
            disabled={loading}
            className="text-xs px-3 py-1.5 rounded border border-[#1e3a1e] text-[#8aab8a] hover:border-[#4ade80] hover:text-[#4ade80] disabled:opacity-40 transition-colors"
          >
            Refresh
          </button>
        </div>
      </div>

      {backendDown && (
        <div className="bg-red-900/20 border border-red-800 rounded-lg px-4 py-3 text-sm text-red-400">
          Backend not reachable — start it with:{' '}
          <code className="text-red-300 bg-red-900/30 px-1 rounded">uvicorn app.main:app --reload</code>
        </div>
      )}

      {/* Stats row */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'High Risk Regions',    value: loading ? '…' : highCount, sub: `of 19 regions` },
          { label: 'Medium Risk Regions',  value: loading ? '…' : medCount },
          { label: 'Avg Fire Probability', value: loading ? '…' : (avgRisk ? `${avgRisk}%` : '—') },
          { label: 'Weather Source',       value: 'FMI', sub: 'Finnish Meteorological Institute' },
        ].map(({ label, value, sub }) => (
          <div key={label} className="bg-[#0d150d] border border-[#1e3a1e] rounded-lg p-4">
            <p className="text-xs text-[#6b8f6b] mb-1">{label}</p>
            <p className="text-xl font-semibold text-[#e2e8e2]">{value ?? '—'}</p>
            {sub && <p className="text-xs text-[#4a6a4a] mt-0.5">{sub}</p>}
          </div>
        ))}
      </div>

      {/* Map + panel */}
      <div className="grid grid-cols-3 gap-5">
        <div className="col-span-2 rounded-xl overflow-hidden border border-[#1e3a1e] relative" style={{ height: 540 }}>
          {loading && (
            <div className="absolute inset-0 z-[1000] flex items-center justify-center bg-[#0a0f0a]/70 pointer-events-none">
              <div className="text-center">
                <div className="w-8 h-8 border-2 border-[#4ade80] border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                <p className="text-sm text-[#8aab8a]">Fetching live FMI weather…</p>
              </div>
            </div>
          )}
          <MapContainer
            center={FINLAND_CENTER}
            zoom={5}
            minZoom={5}
            maxZoom={9}
            maxBounds={FINLAND_BOUNDS}
            maxBoundsViscosity={1.0}
            style={{ height: '100%', width: '100%', background: '#0d150d' }}
          >
            <TileLayer
              url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
              attribution='&copy; <a href="https://carto.com/">CARTO</a>'
            />
            {geojson && (
              <GeoJSON
                key={geojsonKey}
                data={geojson}
                style={styleFeature}
                onEachFeature={onEachFeature}
              />
            )}
          </MapContainer>
        </div>

        {/* Side panel */}
        <div className="flex flex-col gap-4">
          {/* Selected region */}
          <div className="bg-[#0d150d] border border-[#1e3a1e] rounded-lg p-4 flex-1">
            <h2 className="text-sm font-medium text-[#8aab8a] mb-3">
              {selected ? selected.name : 'Region Detail'}
            </h2>
            {!selected && (
              <p className="text-sm text-[#4a6a4a]">Hover or click a region on the map.</p>
            )}
            {selected && (
              <div className="text-sm space-y-1">
                {selected.risk_level ? (
                  <>
                    <div className="flex items-center gap-2 mb-3">
                      <RiskBadge level={selected.risk_level} />
                      <span className="text-[#6b8f6b]">
                        {(selected.fire_risk * 100).toFixed(1)}% probability
                      </span>
                    </div>
                    <Row label="Temperature"   value={selected.features_used?.temperature != null ? `${selected.features_used.temperature} °C` : null} />
                    <Row label="Humidity"      value={selected.features_used?.humidity != null ? `${selected.features_used.humidity} %` : null} />
                    <Row label="Wind Speed"    value={selected.features_used?.wind_speed != null ? `${selected.features_used.wind_speed} m/s` : null} />
                    <Row label="Precipitation" value={selected.features_used?.precipitation != null ? `${selected.features_used.precipitation} mm` : null} />
                    <div className="pt-2 mt-1 border-t border-[#1e3a1e]">
                      <Row label="Weather data" value={selected.fmi_station_name} />
                      <Row label="Confidence"  value={selected.confidence != null ? `${(selected.confidence * 100).toFixed(1)}%` : null} />
                    </div>
                    {selected.warning && (
                      <p className="text-orange-400 text-xs mt-2">{selected.warning}</p>
                    )}
                  </>
                ) : (
                  <p className="text-[#4a6a4a] text-sm">No prediction data for this region yet.</p>
                )}
              </div>
            )}
          </div>

          {/* Ranked region list */}
          <div className="bg-[#0d150d] border border-[#1e3a1e] rounded-lg p-4 overflow-y-auto" style={{ maxHeight: 260 }}>
            <h2 className="text-sm font-medium text-[#8aab8a] mb-2">All Regions</h2>
            {loading && <p className="text-xs text-[#4a6a4a] animate-pulse">Loading…</p>}
            {!loading && regions.length === 0 && (
              <p className="text-xs text-[#4a6a4a]">No data — backend not reachable.</p>
            )}
            {regions
              .slice()
              .sort((a, b) => b.fire_risk - a.fire_risk)
              .map((r) => (
                <button
                  key={r.name}
                  onClick={() => setSelected(r)}
                  className={`w-full flex items-center justify-between px-2 py-1.5 rounded text-sm transition-colors ${
                    selected?.name === r.name ? 'bg-[#1a2e1a]' : 'hover:bg-[#111d11]'
                  }`}
                >
                  <span className="flex items-center gap-2">
                    <span
                      className="w-2 h-2 rounded-full flex-shrink-0"
                      style={{ background: RISK_FILL[r.risk_level]?.fill ?? '#374151' }}
                    />
                    <span className="text-[#c8dcc8]">{r.name}</span>
                  </span>
                  <span className="text-[#6b8f6b] tabular-nums text-xs">
                    {(r.fire_risk * 100).toFixed(0)}%
                  </span>
                </button>
              ))}
          </div>

          {/* Legend */}
          <div className="bg-[#0d150d] border border-[#1e3a1e] rounded-lg p-4">
            <h2 className="text-sm font-medium text-[#8aab8a] mb-2">Risk Scale</h2>
            {[
              ['high',   'Over 60%',  '#ef4444'],
              ['medium', '30 – 60%',  '#fb923c'],
              ['low',    'Under 30%', '#4ade80'],
            ].map(([label, range, color]) => (
              <div key={label} className="flex items-center gap-2 mb-1.5 text-sm">
                <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: color }} />
                <span className="capitalize text-[#8aab8a] w-16">{label}</span>
                <span className="text-[#6b8f6b]">{range}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
