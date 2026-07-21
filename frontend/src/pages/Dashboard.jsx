import { useState, useCallback } from 'react'
import { MapContainer, TileLayer, GeoJSON, CircleMarker, Popup } from 'react-leaflet'

const FINLAND_CENTER = [65.0, 26.0]
const FINLAND_BOUNDS = [[59.3, 19.0], [70.1, 31.6]]

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

export default function Dashboard({
  geojson, riskMap, geojsonKey, loading, backendDown, lastUpdated,
  sensorNodes, setSensorNodes, loadRisk,
}) {
  const [selected, setSelected]               = useState(null)
  const [hardwareReading, setHardwareReading] = useState(null)
  const [hardwareLoading, setHardwareLoading] = useState(false)
  const [hardwareError, setHardwareError]     = useState(null)

  async function triggerHardwareReading() {
    setHardwareLoading(true)
    setHardwareError(null)
    setHardwareReading(null)
    try {
      const res  = await fetch('/api/hardware-reading')
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail ?? `Error ${res.status}`)
      setHardwareReading(data)
      fetch('/api/sensor-nodes').then((r) => r.ok ? r.json() : []).then(setSensorNodes)
    } catch (e) {
      setHardwareError(e.message)
    } finally {
      setHardwareLoading(false)
    }
  }

  const styleFeature = useCallback(
    (feature) => riskStyle(riskMap[feature.properties.nimi]?.risk_level),
    [riskMap],
  )

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

  const regions    = Object.values(riskMap)
  const highCount  = regions.filter((r) => r.risk_level === 'high').length
  const medCount   = regions.filter((r) => r.risk_level === 'medium').length
  const avgRisk    = regions.length
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
            {sensorNodes.map((node) => (
              <CircleMarker
                key={node.node_id}
                center={[node.lat, node.lon]}
                radius={10}
                pane="markerPane"
                pathOptions={{
                  color: '#4ade80',
                  fillColor: '#4ade80',
                  fillOpacity: 0.9,
                  weight: 2,
                }}
                eventHandlers={{
                  popupopen: () => {
                    setHardwareReading(null)
                    setHardwareError(null)
                  },
                }}
              >
                <Popup className="argus-popup">
                  <div style={{ minWidth: 200, fontFamily: 'sans-serif', fontSize: 12 }}>
                    <div style={{ fontWeight: 700, color: '#4ade80', marginBottom: 4 }}>
                      ● Hardware Sensor
                    </div>
                    <div style={{ color: '#c8dcc8', marginBottom: 8 }}>{node.name}</div>

                    {node.latest && !hardwareReading && (
                      <>
                        <div style={{ color: '#6b8f6b', fontSize: 10, marginBottom: 4 }}>Last stored reading</div>
                        <div style={{ color: '#8aab8a' }}>Temp: <span style={{ color: '#e2e8e2' }}>{node.latest.temperature}°C</span></div>
                        <div style={{ color: '#8aab8a' }}>Humidity: <span style={{ color: '#e2e8e2' }}>{node.latest.humidity}%</span></div>
                        <div style={{ color: '#8aab8a', marginBottom: 4 }}>
                          Risk:{' '}
                          <span style={{ color: node.latest.risk_level === 'high' ? '#ef4444' : node.latest.risk_level === 'medium' ? '#fb923c' : '#4ade80', fontWeight: 700, textTransform: 'uppercase' }}>
                            {node.latest.risk_level}
                          </span>
                        </div>
                        <div style={{ color: '#4a6a4a', fontSize: 10, marginBottom: 8 }}>
                          {node.latest.timestamp ? new Date(node.latest.timestamp).toLocaleString('fi-FI') : ''}
                        </div>
                      </>
                    )}

                    {hardwareReading && (
                      <>
                        <div style={{ color: '#6b8f6b', fontSize: 10, marginBottom: 4 }}>Live reading</div>
                        <div style={{ color: '#8aab8a' }}>Temp: <span style={{ color: '#e2e8e2' }}>{hardwareReading.features_used?.temperature}°C</span></div>
                        <div style={{ color: '#8aab8a' }}>Humidity: <span style={{ color: '#e2e8e2' }}>{hardwareReading.features_used?.humidity}%</span></div>
                        <div style={{ color: '#8aab8a' }}>Wind: <span style={{ color: '#e2e8e2' }}>{hardwareReading.features_used?.wind_speed} m/s</span></div>
                        <div style={{ color: '#8aab8a', marginBottom: 4 }}>
                          Risk:{' '}
                          <span style={{ color: hardwareReading.risk_level === 'high' ? '#ef4444' : hardwareReading.risk_level === 'medium' ? '#fb923c' : '#4ade80', fontWeight: 700, textTransform: 'uppercase' }}>
                            {hardwareReading.risk_level}
                          </span>
                          <span style={{ color: '#6b8f6b' }}> · {(hardwareReading.fire_risk * 100).toFixed(1)}%</span>
                        </div>
                        {hardwareReading.alert && (
                          <div style={{ color: '#fb923c', fontSize: 11, marginBottom: 6, padding: '4px 6px', background: 'rgba(251,146,60,0.1)', borderRadius: 4 }}>
                            {hardwareReading.alert.message_en}
                          </div>
                        )}
                      </>
                    )}

                    {hardwareError && (
                      <div style={{ color: '#ef4444', fontSize: 11, marginBottom: 6 }}>{hardwareError}</div>
                    )}

                    {!node.latest && !hardwareReading && (
                      <div style={{ color: '#4a6a4a', marginBottom: 8 }}>No readings yet</div>
                    )}

                    <button
                      onClick={triggerHardwareReading}
                      disabled={hardwareLoading}
                      style={{
                        width: '100%', padding: '5px 0', marginTop: 4,
                        background: hardwareLoading ? '#1a2e1a' : '#166534',
                        color: '#4ade80', border: '1px solid #4ade80',
                        borderRadius: 4, cursor: hardwareLoading ? 'not-allowed' : 'pointer',
                        fontSize: 11, fontWeight: 600,
                      }}
                    >
                      {hardwareLoading ? 'Reading sensors…' : 'Get Live Reading'}
                    </button>
                  </div>
                </Popup>
              </CircleMarker>
            ))}
          </MapContainer>
        </div>

        {/* Side panel */}
        <div className="flex flex-col gap-4">
          <div className="bg-[#0d150d] border border-[#1e3a1e] rounded-lg p-4 flex-1 overflow-y-auto">
            {!selected ? (
              <>
                <h2 className="text-sm font-medium text-[#8aab8a] mb-2">Region Detail</h2>
                <p className="text-sm text-[#4a6a4a]">Click a region name below or on the map.</p>
              </>
            ) : !selected.risk_level ? (
              <>
                <h2 className="text-sm font-medium text-[#e2e8e2] mb-2">{selected.name}</h2>
                <p className="text-[#4a6a4a] text-sm">No prediction data for this region.</p>
              </>
            ) : (
              <>
                <div className="flex items-center gap-2 mb-4">
                  <h2 className="text-sm font-semibold text-[#e2e8e2] flex-1">{selected.name}</h2>
                  <RiskBadge level={selected.risk_level} />
                </div>

                {selected.alert ? (
                  <div className={`p-3 rounded-lg border text-xs leading-relaxed mb-4 ${
                    selected.risk_level === 'high'
                      ? 'bg-red-900/20 border-red-800'
                      : 'bg-orange-900/20 border-orange-800'
                  }`}>
                    <p className={`font-semibold text-xs mb-2 ${selected.risk_level === 'high' ? 'text-red-400' : 'text-orange-400'}`}>
                      Fire Risk Alert
                    </p>
                    <p className="text-[#e2e8e2] mb-2 leading-relaxed">{selected.alert.message_en}</p>
                    <p className="text-[#b0ccb0] border-t border-[#1e3a1e] pt-2 leading-relaxed">{selected.alert.message_fi}</p>
                  </div>
                ) : (
                  <div className="p-3 rounded-lg border border-[#1e3a1e] bg-green-900/10 text-xs text-green-500 mb-4">
                    No alert — fire risk is low for this region.
                  </div>
                )}

                <div className="text-sm space-y-1">
                  <p className="text-xs text-[#6b8f6b] mb-1">Weather data</p>
                  <Row label="Fire probability" value={`${(selected.fire_risk * 100).toFixed(1)}%`} />
                  <Row label="Temperature"   value={selected.features_used?.temperature != null ? `${selected.features_used.temperature} °C` : null} />
                  <Row label="Humidity"      value={selected.features_used?.humidity != null ? `${selected.features_used.humidity} %` : null} />
                  <Row label="Wind Speed"    value={selected.features_used?.wind_speed != null ? `${selected.features_used.wind_speed} m/s` : null} />
                  <Row label="Precipitation" value={selected.features_used?.precipitation != null ? `${selected.features_used.precipitation} mm` : null} />
                  <div className="pt-2 mt-1 border-t border-[#1e3a1e]">
                    <Row label="Source"     value={selected.fmi_station_name} />
                    <Row label="Confidence" value={selected.confidence != null ? `${(selected.confidence * 100).toFixed(1)}%` : null} />
                  </div>
                  {selected.warning && (
                    <p className="text-orange-400 text-xs mt-2">{selected.warning}</p>
                  )}
                </div>
              </>
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
