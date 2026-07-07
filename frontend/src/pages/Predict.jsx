import { useState } from 'react'

const MODES = {
  fmi_only: { label: 'FMI Only (Mode A)', desc: 'All weather data fetched automatically from FMI. Just provide coordinates.' },
  hardware_fmi: { label: 'Hardware + FMI (Mode B)', desc: 'Your sensor provides temperature, humidity, wind speed. Precipitation fetched from FMI.' },
  hardware_only: { label: 'Hardware Only (Mode C)', desc: 'All sensor values provided manually. No FMI calls made.' },
}

const RISK_COLORS = {
  low: { bg: 'bg-green-900/30', border: 'border-green-700', text: 'text-green-400', bar: 'bg-green-500' },
  medium: { bg: 'bg-orange-900/30', border: 'border-orange-700', text: 'text-orange-400', bar: 'bg-orange-500' },
  high: { bg: 'bg-red-900/30', border: 'border-red-700', text: 'text-red-400', bar: 'bg-red-500' },
}

function Field({ label, name, value, onChange, required, step = '0.01', placeholder }) {
  return (
    <div>
      <label className="block text-xs text-[#6b8f6b] mb-1">
        {label} {required && <span className="text-[#4ade80]">*</span>}
      </label>
      <input
        type="number"
        step={step}
        name={name}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        className="w-full bg-[#0d150d] border border-[#1e3a1e] rounded px-3 py-2 text-sm text-[#e2e8e2] placeholder-[#3a5a3a] focus:outline-none focus:border-[#4ade80] transition-colors"
      />
    </div>
  )
}

export default function Predict() {
  const [mode, setMode] = useState('fmi_only')
  const [form, setForm] = useState({
    station_lat: '', station_lon: '',
    temperature: '', humidity: '', wind_speed: '', precipitation: '',
  })
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  function handleChange(e) {
    setForm((f) => ({ ...f, [e.target.name]: e.target.value }))
  }

  function buildBody() {
    const body = {
      station_lat: parseFloat(form.station_lat),
      station_lon: parseFloat(form.station_lon),
    }
    if (mode === 'hardware_fmi' || mode === 'hardware_only') {
      body.temperature = parseFloat(form.temperature)
      body.humidity = parseFloat(form.humidity)
      body.wind_speed = parseFloat(form.wind_speed)
    }
    if (mode === 'hardware_only') {
      body.precipitation = parseFloat(form.precipitation)
    }
    return body
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await fetch('/api/predict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildBody()),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail ?? `Error ${res.status}`)
      setResult(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const risk = result?.risk_level
  const riskStyle = RISK_COLORS[risk] ?? RISK_COLORS.low

  return (
    <div className="max-w-2xl mx-auto flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold text-[#e2e8e2]">Fire Risk Prediction</h1>
        <p className="text-sm text-[#6b8f6b] mt-0.5">Manually query the model for any location and sensor reading.</p>
      </div>

      {/* Mode selector */}
      <div className="grid grid-cols-3 gap-3">
        {Object.entries(MODES).map(([key, { label, desc }]) => (
          <button
            key={key}
            onClick={() => setMode(key)}
            className={`text-left p-3 rounded-lg border text-sm transition-colors ${
              mode === key
                ? 'border-[#4ade80] bg-[#0d1f0d] text-[#e2e8e2]'
                : 'border-[#1e3a1e] bg-[#0d150d] text-[#8aab8a] hover:border-[#2d5a2d]'
            }`}
          >
            <p className="font-medium mb-1">{label}</p>
            <p className="text-xs text-[#6b8f6b] leading-snug">{desc}</p>
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="bg-[#0d150d] border border-[#1e3a1e] rounded-lg p-5 flex flex-col gap-4">
        <div className="grid grid-cols-2 gap-4">
          <Field label="Latitude" name="station_lat" value={form.station_lat} onChange={handleChange} required placeholder="e.g. 60.17" />
          <Field label="Longitude" name="station_lon" value={form.station_lon} onChange={handleChange} required placeholder="e.g. 24.94" />
        </div>

        {(mode === 'hardware_fmi' || mode === 'hardware_only') && (
          <div className="grid grid-cols-3 gap-4">
            <Field label="Temperature (°C)" name="temperature" value={form.temperature} onChange={handleChange} required placeholder="e.g. 22.5" />
            <Field label="Humidity (%)" name="humidity" value={form.humidity} onChange={handleChange} required placeholder="e.g. 55" />
            <Field label="Wind Speed (m/s)" name="wind_speed" value={form.wind_speed} onChange={handleChange} required placeholder="e.g. 3.2" />
          </div>
        )}

        {mode === 'hardware_only' && (
          <div className="grid grid-cols-2 gap-4">
            <Field label="Precipitation (mm)" name="precipitation" value={form.precipitation} onChange={handleChange} required placeholder="e.g. 0.0" />
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="mt-1 bg-[#166534] hover:bg-[#15803d] disabled:opacity-50 text-[#e2e8e2] font-medium py-2.5 rounded-lg transition-colors text-sm"
        >
          {loading ? 'Running prediction...' : 'Run Prediction'}
        </button>
      </form>

      {error && (
        <div className="bg-red-900/20 border border-red-800 rounded-lg p-4 text-sm text-red-400">
          {error}
        </div>
      )}

      {result && (
        <div className={`${riskStyle.bg} border ${riskStyle.border} rounded-lg p-5`}>
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-[#e2e8e2]">Result</h2>
            <span className={`px-3 py-1 rounded-full text-sm font-medium border ${riskStyle.border} ${riskStyle.text}`}>
              {risk?.toUpperCase()} RISK
            </span>
          </div>

          {/* Probability bar */}
          <div className="mb-4">
            <div className="flex justify-between text-xs text-[#6b8f6b] mb-1">
              <span>Fire Probability</span>
              <span>{(result.fire_risk * 100).toFixed(1)}%</span>
            </div>
            <div className="h-2 bg-[#0a0f0a] rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${riskStyle.bar}`}
                style={{ width: `${result.fire_risk * 100}%` }}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-x-8 gap-y-1.5 text-sm">
            {Object.entries(result.features_used).map(([k, v]) => (
              <div key={k} className="flex justify-between gap-4">
                <span className="text-[#6b8f6b] capitalize">{k.replace(/_/g, ' ')}</span>
                <span className="text-[#c8dcc8]">{v ?? '—'}</span>
              </div>
            ))}
          </div>

          <div className="mt-3 pt-3 border-t border-[#1e3a1e] grid grid-cols-2 gap-x-8 text-sm">
            <div className="flex justify-between gap-4">
              <span className="text-[#6b8f6b]">Input mode</span>
              <span className="text-[#c8dcc8]">{result.input_mode}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-[#6b8f6b]">Confidence</span>
              <span className="text-[#c8dcc8]">{(result.confidence * 100).toFixed(1)}%</span>
            </div>
            {result.fmi_station_name && (
              <div className="flex justify-between gap-4">
                <span className="text-[#6b8f6b]">FMI station</span>
                <span className="text-[#c8dcc8] text-right">{result.fmi_station_name}</span>
              </div>
            )}
            {result.distance_to_station_km != null && (
              <div className="flex justify-between gap-4">
                <span className="text-[#6b8f6b]">Station distance</span>
                <span className="text-[#c8dcc8]">{result.distance_to_station_km} km</span>
              </div>
            )}
          </div>

          {result.warning && (
            <p className="mt-3 text-xs text-orange-400">{result.warning}</p>
          )}
        </div>
      )}
    </div>
  )
}
