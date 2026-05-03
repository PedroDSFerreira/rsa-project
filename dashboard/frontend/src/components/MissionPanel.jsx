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

  return (
    <div style={PANEL}>
      <div style={SECTION}>
        <div style={TITLE}>Mission</div>
        <div style={ROW}><span>Tick</span><span>{tick}</span></div>
        <div style={ROW}><span>Drones</span><span>{drones.length} / {meta?.num_drones ?? '?'}</span></div>
        <div style={ROW}><span>Sensors</span><span>{sensors.length} / {meta?.num_sensors ?? '?'}</span></div>
        <div style={ROW}><span>Links</span><span>{links.length}</span></div>
      </div>

      <div style={SECTION}>
        <div style={TITLE}>Entities</div>
        {entityList.length === 0 && <div style={{ fontSize: '12px', color: '#888' }}>Waiting for announcements…</div>}
        {entityList.map((e) => {
          const idx = e.container_name?.match(/-([0-9]+)$/)?.[1] ?? e.station_id
          const label = e.entity_type === 'base_station' ? 'base station' : `${e.entity_type} #${idx}`
          return (
            <div key={e.station_id} style={{ ...ROW, alignItems: 'center' }}>
              <span style={{ fontSize: '12px' }}>
                <span style={{ color: e.entity_type === 'drone' ? '#4fc3f7' : '#81c784' }}>● </span>
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
