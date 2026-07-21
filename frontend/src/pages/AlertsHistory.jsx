import { useState } from 'react'

const RISK_STYLES = {
  low:    'text-green-400',
  medium: 'text-orange-400',
  high:   'text-red-400',
}

export default function AlertsHistory({ alerts, loading, error }) {
  const [expanded, setExpanded] = useState(null)

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-[#e2e8e2]">Alerts History</h1>
          <p className="text-sm text-[#6b8f6b] mt-0.5">AI-generated alerts logged for medium and high risk predictions.</p>
        </div>
        {!loading && !error && (
          <span className="text-xs text-[#6b8f6b]">{alerts.length} alerts</span>
        )}
      </div>

      <div className="bg-[#0d150d] border border-[#1e3a1e] rounded-lg overflow-hidden">
        {loading && <div className="p-8 text-center text-sm text-[#6b8f6b] animate-pulse">Loading...</div>}
        {error && (
          <div className="p-8 text-center text-sm text-red-400">
            Could not load alerts: {error}
            <p className="text-xs text-[#4a6a4a] mt-1">Make sure the backend is running.</p>
          </div>
        )}
        {!loading && !error && alerts.length === 0 && (
          <div className="p-8 text-center text-sm text-[#4a6a4a]">
            No alerts yet — alerts are generated for medium and high risk predictions.
          </div>
        )}
        {!loading && !error && alerts.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1e3a1e] text-[#6b8f6b] text-xs">
                <th className="text-left px-4 py-3 font-medium">Timestamp</th>
                <th className="text-center px-4 py-3 font-medium">Risk</th>
                <th className="text-right px-4 py-3 font-medium">Temp</th>
                <th className="text-right px-4 py-3 font-medium">Humidity</th>
                <th className="text-right px-4 py-3 font-medium">Wind</th>
                <th className="text-left px-4 py-3 font-medium">Alert (EN)</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((a, i) => (
                <>
                  <tr
                    key={a.id ?? i}
                    onClick={() => setExpanded(expanded === i ? null : i)}
                    className="border-b border-[#111d11] hover:bg-[#0d1a0d] transition-colors cursor-pointer"
                  >
                    <td className="px-4 py-3 text-[#6b8f6b] tabular-nums text-xs">
                      {a.timestamp ? new Date(a.timestamp).toLocaleString('fi-FI') : '—'}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className={`font-semibold capitalize text-xs ${RISK_STYLES[a.severity] ?? 'text-[#8aab8a]'}`}>
                        {a.severity ?? '—'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right text-[#c8dcc8]">{a.temperature != null ? `${a.temperature}°C` : '—'}</td>
                    <td className="px-4 py-3 text-right text-[#c8dcc8]">{a.humidity != null ? `${a.humidity}%` : '—'}</td>
                    <td className="px-4 py-3 text-right text-[#c8dcc8]">{a.wind_speed != null ? `${a.wind_speed} m/s` : '—'}</td>
                    <td className="px-4 py-3 text-[#8aab8a] max-w-xs">
                      <p className="truncate">{a.message_en}</p>
                    </td>
                  </tr>
                  {expanded === i && (
                    <tr key={`${i}-exp`} className="border-b border-[#1e3a1e] bg-[#0a120a]">
                      <td colSpan={6} className="px-4 py-4">
                        <div className="grid grid-cols-2 gap-4 text-sm">
                          <div>
                            <p className="text-xs text-[#6b8f6b] mb-1">English</p>
                            <p className="text-[#e2e8e2] leading-relaxed">{a.message_en}</p>
                          </div>
                          <div>
                            <p className="text-xs text-[#6b8f6b] mb-1">Suomi</p>
                            <p className="text-[#e2e8e2] leading-relaxed">{a.message_fi}</p>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
