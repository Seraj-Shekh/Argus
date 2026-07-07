import { useState, useEffect } from 'react'

const RISK_STYLES = {
  low: 'text-green-400',
  medium: 'text-orange-400',
  high: 'text-red-400',
}

export default function AlertsHistory() {
  const [readings, setReadings] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch('/api/sensor-readings')
      .then((r) => {
        if (!r.ok) throw new Error(`Server returned ${r.status}`)
        return r.json()
      })
      .then((data) => {
        setReadings(Array.isArray(data) ? data : data.readings ?? [])
        setLoading(false)
      })
      .catch((e) => {
        setError(e.message)
        setLoading(false)
      })
  }, [])

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-[#e2e8e2]">Alerts History</h1>
          <p className="text-sm text-[#6b8f6b] mt-0.5">Past sensor readings and risk predictions logged to the database.</p>
        </div>
        {!loading && !error && (
          <span className="text-xs text-[#6b8f6b]">{readings.length} records</span>
        )}
      </div>

      <div className="bg-[#0d150d] border border-[#1e3a1e] rounded-lg overflow-hidden">
        {loading && (
          <div className="p-8 text-center text-sm text-[#6b8f6b] animate-pulse">Loading...</div>
        )}
        {error && (
          <div className="p-8 text-center text-sm text-red-400">
            Could not load data: {error}
            <p className="text-xs text-[#4a6a4a] mt-1">Make sure the backend is running and the /api/sensor-readings endpoint exists.</p>
          </div>
        )}
        {!loading && !error && readings.length === 0 && (
          <div className="p-8 text-center text-sm text-[#4a6a4a]">
            No readings yet. Use the Dashboard or Predict page to generate some.
          </div>
        )}
        {!loading && !error && readings.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1e3a1e] text-[#6b8f6b] text-xs">
                <th className="text-left px-4 py-3 font-medium">Timestamp</th>
                <th className="text-left px-4 py-3 font-medium">Node</th>
                <th className="text-right px-4 py-3 font-medium">Temp (°C)</th>
                <th className="text-right px-4 py-3 font-medium">Humidity (%)</th>
                <th className="text-right px-4 py-3 font-medium">Wind (m/s)</th>
                <th className="text-center px-4 py-3 font-medium">Risk Level</th>
              </tr>
            </thead>
            <tbody>
              {readings.map((r, i) => (
                <tr
                  key={r.id ?? i}
                  className="border-b border-[#111d11] hover:bg-[#0d1a0d] transition-colors"
                >
                  <td className="px-4 py-3 text-[#6b8f6b] tabular-nums">
                    {r.timestamp ? new Date(r.timestamp).toLocaleString('fi-FI') : '—'}
                  </td>
                  <td className="px-4 py-3 text-[#8aab8a]">{r.node_id ?? '—'}</td>
                  <td className="px-4 py-3 text-right text-[#c8dcc8]">{r.temperature ?? '—'}</td>
                  <td className="px-4 py-3 text-right text-[#c8dcc8]">{r.humidity ?? '—'}</td>
                  <td className="px-4 py-3 text-right text-[#c8dcc8]">{r.wind_speed ?? '—'}</td>
                  <td className="px-4 py-3 text-center">
                    {r.risk_level ? (
                      <span className={`font-medium capitalize ${RISK_STYLES[r.risk_level] ?? 'text-[#8aab8a]'}`}>
                        {r.risk_level}
                      </span>
                    ) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
