import { useEffect, useState } from 'react'
import { useSim, API_URL } from '../context/SimContext'

const PANEL = {
  width: '280px',
  background: '#16213e',
  padding: '16px',
  overflowY: 'auto',
  display: 'flex',
  flexDirection: 'column',
  gap: '12px',
  borderLeft: '1px solid #0f3460',
}

const SECTION = { background: '#0f3460', borderRadius: '6px', padding: '12px' }
const TITLE = { fontSize: '11px', textTransform: 'uppercase', letterSpacing: '1px', color: '#90caf9', marginBottom: '8px' }
const ROW = { display: 'flex', justifyContent: 'space-between', fontSize: '13px', marginBottom: '4px' }
const BTN = { width: '100%', padding: '10px', borderRadius: '6px', border: 'none', fontSize: '13px', fontWeight: 'bold', cursor: 'pointer', background: '#1b5e20', color: '#fff' }
const BTN_SENT = { ...BTN, background: '#37474f', cursor: 'default' }
const SELECT = {
  width: '100%', padding: '8px', borderRadius: '6px', border: '1px solid #1565c0',
  background: '#0d1b2a', color: '#e0e0e0', fontSize: '13px', marginBottom: '8px', cursor: 'pointer',
}

export default function MissionPanel() {
  const { meta, entities, links, tick, deliveries } = useSim()
  const [started, setStarted] = useState(false)
  const [algorithm, setAlgorithm] = useState('boustrophedon')
  const [availableAlgorithms, setAvailableAlgorithms] = useState(['boustrophedon', 'greedy'])

  useEffect(() => {
    fetch(`${API_URL}/algorithms`)
      .then((r) => r.json())
      .then((list) => { setAvailableAlgorithms(list); setAlgorithm(list[0]) })
      .catch(() => {})
  }, [])

  function handleStart() {
    fetch(`${API_URL}/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ algorithm }),
    }).then(() => setStarted(true))
  }

  const entityList = Object.values(entities)
  const drones = entityList.filter((e) => e.entity_type === 'drone')
  const sensors = entityList.filter((e) => e.entity_type === 'sensor')
  const expected = (meta.num_drones ?? 0) + (meta.num_sensors ?? 0) + 1
  const allDiscovered = expected > 1 && entityList.length >= expected

  const statusColor = allDiscovered ? '#81c784' : entityList.length > 0 ? '#ffb74d' : '#90caf9'
  const statusText = allDiscovered ? '● Active' : entityList.length > 0 ? '○ Discovering entities…' : '○ Waiting…'

  return (
    <div style={PANEL}>
      <div style={SECTION}>
        <div style={TITLE}>Control</div>
        <select
          style={SELECT}
          value={algorithm}
          onChange={(e) => setAlgorithm(e.target.value)}
          disabled={started}
        >
          {availableAlgorithms.map((a) => (
            <option key={a} value={a}>{a.charAt(0).toUpperCase() + a.slice(1)}</option>
          ))}
        </select>
        <button style={started ? BTN_SENT : BTN} onClick={handleStart} disabled={started}>
          {started ? `Mission started (${algorithm})` : 'Start mission'}
        </button>
      </div>
      <div style={SECTION}>
        <div style={TITLE}>Status</div>
        <div style={{ fontSize: '13px', color: statusColor }}>{statusText}</div>
      </div>

      <div style={SECTION}>
        <div style={TITLE}>Mission</div>
        <div style={ROW}><span>Tick</span><span>{tick}</span></div>
        <div style={ROW}><span>Drones</span><span>{drones.length} / {meta?.num_drones ?? '?'}</span></div>
        <div style={ROW}><span>Sensors</span><span>{sensors.length} / {meta?.num_sensors ?? '?'}</span></div>
        <div style={ROW}><span>Active links</span><span>{links.length}</span></div>
      </div>

      <div style={SECTION}>
        <div style={TITLE}>Data delivery</div>
        {(() => {
          const entries = Object.entries(deliveries)
          const unique = entries.length
          const duplicates = entries.filter(([, count]) => count > 1)
          const total = entries.reduce((sum, [, count]) => sum + count, 0)
          const numSensors = meta?.num_sensors ?? 0
          return (
            <>
              <div style={ROW}>
                <span>Unique sensors</span>
                <span>{unique} / {numSensors || '?'}</span>
              </div>
              {duplicates.length > 0 && (
                <div style={{ ...ROW, color: '#ef9a9a' }}>
                  <span>Duplicate collections</span>
                  <span>{total - unique}</span>
                </div>
              )}
              <div style={{ background: '#1a237e', borderRadius: '4px', overflow: 'hidden', height: '8px', marginTop: '4px' }}>
                <div style={{
                  height: '100%',
                  width: `${numSensors ? (unique / numSensors) * 100 : 0}%`,
                  background: duplicates.length > 0 ? '#ef9a9a' : '#42a5f5',
                  transition: 'width 0.4s ease',
                }} />
              </div>
              {duplicates.length > 0 && (
                <div style={{ fontSize: '11px', color: '#ef9a9a', marginTop: '6px' }}>
                  {duplicates.map(([id, count]) => `S${id}: ×${count}`).join('  ')}
                </div>
              )}
            </>
          )
        })()}
      </div>

      <div style={SECTION}>
        <div style={TITLE}>Grid legend</div>
        {[
          { color: '#90caf9', label: 'Claimed' },
          { color: '#a5d6a7', label: 'Visited' },
          { color: '#ffb300', label: 'Sensor found' },
        ].map(({ color, label }) => (
          <div key={label} style={{ ...ROW, alignItems: 'center' }}>
            <span style={{ display: 'inline-block', width: 12, height: 12, background: color, borderRadius: 2, marginRight: 6 }} />
            <span style={{ fontSize: '12px', flex: 1 }}>{label}</span>
          </div>
        ))}
      </div>

      <div style={SECTION}>
        <div style={TITLE}>Entities</div>
        {entityList.length === 0 && <div style={{ fontSize: '12px', color: '#888' }}>Waiting for announcements…</div>}
        {entityList.map((e) => {
          const idx = e.container_name?.match(/-([0-9]+)$/)?.[1] ?? e.station_id
          const label = e.entity_type === 'base_station' ? 'base station' : `${e.entity_type} #${idx}`
          const color = e.entity_type === 'drone' ? '#4fc3f7' : e.entity_type === 'base_station' ? '#ffb74d' : '#81c784'
          return (
            <div key={e.station_id} style={{ ...ROW, alignItems: 'center' }}>
              <span style={{ fontSize: '12px' }}>
                <span style={{ color }}>● </span>
                {label}
              </span>
              <span style={{ fontSize: '11px', color: '#aaa' }}>{e.lat.toFixed(4)}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
