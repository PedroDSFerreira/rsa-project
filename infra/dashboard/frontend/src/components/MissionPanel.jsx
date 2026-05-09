import { useSim } from '../context/SimContext'

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

export default function MissionPanel() {
  const { meta, entities, links, tick } = useSim()

  const entityList = Object.values(entities)
  const drones = entityList.filter((e) => e.entity_type === 'drone')
  const sensors = entityList.filter((e) => e.entity_type === 'sensor')
  const running = drones.length > 0

  return (
    <div style={PANEL}>
      <div style={SECTION}>
        <div style={TITLE}>Status</div>
        <div style={{ fontSize: '13px', color: running ? '#81c784' : '#ffb74d' }}>
          {running ? '● Mission running' : '○ Waiting for entities…'}
        </div>
      </div>

      <div style={SECTION}>
        <div style={TITLE}>Mission</div>
        <div style={ROW}><span>Tick</span><span>{tick}</span></div>
        <div style={ROW}><span>Drones</span><span>{drones.length} / {meta?.num_drones ?? '?'}</span></div>
        <div style={ROW}><span>Sensors</span><span>{sensors.length} / {meta?.num_sensors ?? '?'}</span></div>
        <div style={ROW}><span>Active links</span><span>{links.length}</span></div>
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
