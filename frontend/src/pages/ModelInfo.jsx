import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  RadarChart, PolarGrid, PolarAngleAxis, Radar,
} from 'recharts'

// Static — from train_model.py results
const FEATURE_IMPORTANCES = [
  { feature: 'Humidity', importance: 27.1 },
  { feature: 'Temperature', importance: 21.3 },
  { feature: 'Day of Year', importance: 17.4 },
  { feature: 'Wind Speed', importance: 9.2 },
  { feature: 'Month', importance: 8.1 },
  { feature: 'Station Lat', importance: 7.8 },
  { feature: 'Station Lon', importance: 5.4 },
  { feature: 'Precipitation', importance: 3.7 },
]

const METRICS = [
  { label: 'Accuracy', value: '86%', sub: 'Overall correct predictions' },
  { label: 'ROC-AUC', value: '0.928', sub: 'Discriminative ability (1.0 = perfect)' },
  { label: 'Fire F1', value: '0.80', sub: 'Precision × recall balance for fire class' },
  { label: 'Training Rows', value: '20,833', sub: 'Fire + non-fire events 2015–2024' },
]

const RADAR_DATA = FEATURE_IMPORTANCES.map((d) => ({
  subject: d.feature,
  importance: d.importance,
}))

function MetricCard({ label, value, sub }) {
  return (
    <div className="bg-[#0d150d] border border-[#1e3a1e] rounded-lg p-4">
      <p className="text-xs text-[#6b8f6b] mb-1">{label}</p>
      <p className="text-2xl font-semibold text-[#4ade80]">{value}</p>
      <p className="text-xs text-[#4a6a4a] mt-1">{sub}</p>
    </div>
  )
}

const TooltipStyle = {
  contentStyle: { background: '#0d150d', border: '1px solid #1e3a1e', borderRadius: 8 },
  labelStyle: { color: '#8aab8a' },
  itemStyle: { color: '#4ade80' },
}

export default function ModelInfo() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold text-[#e2e8e2]">Model Information</h1>
        <p className="text-sm text-[#6b8f6b] mt-0.5">
          Random Forest (300 trees, balanced class weights) trained on EFFIS fire events matched to FMI weather observations.
        </p>
      </div>

      <div className="grid grid-cols-4 gap-4">
        {METRICS.map((m) => <MetricCard key={m.label} {...m} />)}
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* Feature importance bar chart */}
        <div className="bg-[#0d150d] border border-[#1e3a1e] rounded-lg p-5">
          <h2 className="text-sm font-medium text-[#8aab8a] mb-4">Feature Importance</h2>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart
              data={FEATURE_IMPORTANCES}
              layout="vertical"
              margin={{ left: 16, right: 24, top: 0, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#1e3a1e" horizontal={false} />
              <XAxis type="number" tick={{ fill: '#6b8f6b', fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
              <YAxis type="category" dataKey="feature" tick={{ fill: '#8aab8a', fontSize: 11 }} width={80} />
              <Tooltip {...TooltipStyle} formatter={(v) => [`${v}%`, 'Importance']} />
              <Bar dataKey="importance" fill="#4ade80" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Radar chart */}
        <div className="bg-[#0d150d] border border-[#1e3a1e] rounded-lg p-5">
          <h2 className="text-sm font-medium text-[#8aab8a] mb-4">Feature Coverage (Radar)</h2>
          <ResponsiveContainer width="100%" height={260}>
            <RadarChart data={RADAR_DATA}>
              <PolarGrid stroke="#1e3a1e" />
              <PolarAngleAxis dataKey="subject" tick={{ fill: '#6b8f6b', fontSize: 10 }} />
              <Radar name="Importance" dataKey="importance" stroke="#4ade80" fill="#4ade80" fillOpacity={0.25} />
              <Tooltip {...TooltipStyle} formatter={(v) => [`${v}%`, 'Importance']} />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Model details */}
      <div className="bg-[#0d150d] border border-[#1e3a1e] rounded-lg p-5">
        <h2 className="text-sm font-medium text-[#8aab8a] mb-4">Pipeline Details</h2>
        <div className="grid grid-cols-3 gap-6 text-sm">
          <Detail label="Algorithm" value="Random Forest Classifier" />
          <Detail label="Trees" value="300 estimators" />
          <Detail label="Class Weights" value="Balanced (fire is rare)" />
          <Detail label="Missing Values" value="Median imputation" />
          <Detail label="Train/Test Split" value="80% / 20%, stratified" />
          <Detail label="Fire Events Source" value="EFFIS (EU Fire Database)" />
          <Detail label="Weather Source" value="FMI Open Data WFS API" />
          <Detail label="Stations in Dataset" value="157 of 199 available stations" />
          <Detail label="Date Range" value="2015–2026" />
        </div>

        <div className="mt-5 p-3 bg-[#0a120a] border border-[#1e3a1e] rounded text-xs text-[#6b8f6b] leading-relaxed">
          <strong className="text-[#8aab8a]">Note on probability calibration:</strong>{' '}
          The model uses <code className="text-[#4ade80]">class_weight="balanced"</code> to handle the fire/non-fire
          class imbalance. This inflates raw fire-class probabilities — a reading of 60–70% should be
          interpreted as high-risk conditions, not a literal 60–70% chance of ignition. The model predicts
          fire-favorable weather, not the presence of an ignition source.
        </div>
      </div>
    </div>
  )
}

function Detail({ label, value }) {
  return (
    <div>
      <p className="text-[#6b8f6b] text-xs mb-0.5">{label}</p>
      <p className="text-[#c8dcc8]">{value}</p>
    </div>
  )
}
