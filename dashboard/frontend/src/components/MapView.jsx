import { MapContainer, TileLayer, Marker, Popup, Polyline } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import L from 'leaflet'
import { useSim } from '../context/SimContext'

delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

const ENTITY_COLORS = { drone: '#4fc3f7', sensor: '#81c784', base_station: '#ffb74d' }

function entityIcon(type) {
  const color = ENTITY_COLORS[type] ?? '#e0e0e0'
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">
    <circle cx="12" cy="12" r="10" fill="${color}" stroke="#fff" stroke-width="2"/>
  </svg>`
  return L.divIcon({ html: svg, className: '', iconSize: [24, 24], iconAnchor: [12, 12] })
}

export default function MapView() {
  const { meta, entities, links } = useSim()

  const origin = meta?.map
    ? [meta.map.origin_lat, meta.map.origin_lng]
    : [40.630, -8.660]

  const entityList = Object.values(entities)

  const linkLines = links.map(([idA, idB]) => {
    const a = entities[idA]
    const b = entities[idB]
    if (!a || !b) return null
    return <Polyline key={`${idA}-${idB}`} positions={[[a.lat, a.lng], [b.lat, b.lng]]} color="#4fc3f7" opacity={0.6} weight={1.5} />
  }).filter(Boolean)

  return (
    <MapContainer center={origin} zoom={15} style={{ flex: 1, height: '100%' }}>
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution="© OpenStreetMap contributors"
      />
      {entityList.map((e) => (
        <Marker key={e.station_id} position={[e.lat, e.lng]} icon={entityIcon(e.entity_type)}>
          <Popup>
            <strong>{e.entity_type} {e.station_id}</strong><br />
            {e.container_name}<br />
            {e.lat.toFixed(5)}, {e.lng.toFixed(5)}
          </Popup>
        </Marker>
      ))}
      {linkLines}
    </MapContainer>
  )
}
