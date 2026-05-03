import { MapContainer, TileLayer, Marker, Popup, Polyline, Rectangle } from 'react-leaflet'
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

const DEFAULT_SW_LAT = 40.630
const DEFAULT_SW_LNG = -8.660
const DEFAULT_WIDTH_M = 1000
const DEFAULT_HEIGHT_M = 1000

function simAreaBounds(meta) {
  const s = meta?.sim_area ?? meta?.map
  const swLat = s?.sw_lat ?? DEFAULT_SW_LAT
  const swLng = s?.sw_lng ?? DEFAULT_SW_LNG
  const widthM = s?.width_m ?? DEFAULT_WIDTH_M
  const heightM = s?.height_m ?? DEFAULT_HEIGHT_M
  const neLat = swLat + heightM / 111000
  const neLng = swLng + widthM / (111000 * Math.cos(swLat * Math.PI / 180))
  return [[swLat, swLng], [neLat, neLng]]
}

function simAreaCenter(meta) {
  const s = meta?.sim_area ?? meta?.map
  const swLat = s?.sw_lat ?? DEFAULT_SW_LAT
  const swLng = s?.sw_lng ?? DEFAULT_SW_LNG
  const widthM = s?.width_m ?? DEFAULT_WIDTH_M
  const heightM = s?.height_m ?? DEFAULT_HEIGHT_M
  return [
    swLat + (heightM / 2) / 111000,
    swLng + (widthM / 2) / (111000 * Math.cos(swLat * Math.PI / 180)),
  ]
}

export default function MapView() {
  const { meta, entities, links } = useSim()

  const center = simAreaCenter(meta)
  const areaBounds = simAreaBounds(meta)

  const entityList = Object.values(entities)

  const linkLines = links.map(([idA, idB]) => {
    const a = entities[idA]
    const b = entities[idB]
    if (!a || !b) return null
    return <Polyline key={`${idA}-${idB}`} positions={[[a.lat, a.lng], [b.lat, b.lng]]} color="#4fc3f7" opacity={0.6} weight={1.5} />
  }).filter(Boolean)

  return (
    <MapContainer center={center} zoom={15} style={{ flex: 1, height: '100%' }}>
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution="© OpenStreetMap contributors"
      />
      <Rectangle
        bounds={areaBounds}
        pathOptions={{ color: '#42a5f5', weight: 3, fillColor: '#90caf9', fillOpacity: 0.15, dashArray: '10 6' }}
      />
      {entityList.map((e) => {
        const idx = e.container_name?.match(/-([0-9]+)$/)?.[1] ?? e.station_id
        return (
          <Marker key={e.station_id} position={[e.lat, e.lng]} icon={entityIcon(e.entity_type)}>
            <Popup>
              <strong>{e.entity_type} #{idx}</strong><br />
              {e.lat.toFixed(5)}, {e.lng.toFixed(5)}<br />
              <small style={{color:'#888'}}>id: {e.station_id}</small>
            </Popup>
          </Marker>
        )
      })}
      {linkLines}
    </MapContainer>
  )
}
