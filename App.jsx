import { useState, useEffect } from 'react'
import Dashboard from './Dashboard.jsx'

const API_BASE = import.meta.env.VITE_API_URL || ''

async function fetchStats(hours = 24) {
  try {
    const r = await fetch(`${API_BASE}/v1/stats?hours=${hours}`)
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    return await r.json()
  } catch {
    return null
  }
}

async function fetchLogs(limit = 50, blockedOnly = false) {
  try {
    const params = new URLSearchParams({ limit })
    if (blockedOnly) params.set('blocked_only', 'true')
    const r = await fetch(`${API_BASE}/v1/logs?${params}`)
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    const data = await r.json()
    return data.logs || []
  } catch {
    return []
  }
}

async function fetchHealth() {
  try {
    const r = await fetch(`${API_BASE}/health`)
    if (!r.ok) throw new Error()
    return await r.json()
  } catch {
    return null
  }
}

export default function App() {
  const [stats, setStats] = useState(null)
  const [logs, setLogs] = useState([])
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)

  async function refresh() {
    const [s, l, h] = await Promise.all([fetchStats(), fetchLogs(), fetchHealth()])
    setStats(s)
    setLogs(l)
    setHealth(h)
    setLoading(false)
  }

  useEffect(() => {
    refresh()
    const iv = setInterval(refresh, 30_000) // refresh every 30s
    return () => clearInterval(iv)
  }, [])

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', background: '#07080F', color: '#7B829E', fontSize: 14, fontFamily: 'system-ui' }}>
        Connecting to ShieldAI API...
      </div>
    )
  }

  return <Dashboard stats={stats} logs={logs} health={health} onRefresh={refresh} />
}
