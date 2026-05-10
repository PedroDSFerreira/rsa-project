import { useMemo } from 'react'
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

const CELL_STYLES = {
  1: { color: '#4fc3f7', fillColor: '#90caf9', fillOpacity: 0.35, weight: 0 }, // CLAIMED
  2: { color: '#81c784', fillColor: '#a5d6a7', fillOpacity: 0.45, weight: 0 }, // VISITED
  3: { color: '#ff8f00', fillColor: '#ffb300', fillOpacity: 0.7,  weight: 0 }, // SENSOR_FOUND
}

function cellBounds(grid_map, cellIndex) {
  const { sw_lat, sw_lng, width_m, height_m, cell_size_m } = grid_map
  const cols = Math.ceil(width_m / cell_size_m)
  const row = Math.floor(cellIndex / cols)
  const col = cellIndex % cols
  const mPerLat = 111000
  const mPerLng = 111000 * Math.cos(sw_lat * Math.PI / 180)
  const s = sw_lat + row * cell_size_m / mPerLat
  const w = sw_lng + col * cell_size_m / mPerLng
  const n = s + cell_size_m / mPerLat
  const e = w + cell_size_m / mPerLng
  return [[s, w], [n, e]]
}

function entityIcon(type, label) {
  const color = ENTITY_COLORS[type] ?? '#e0e0e0'
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 28 28">
    <circle cx="14" cy="14" r="12" fill="${color}" stroke="#fff" stroke-width="2"/>
    <text x="14" y="18" text-anchor="middle" font-size="9" font-family="monospace" font-weight="bold" fill="#fff">${label}</text>
  </svg>`
  return L.divIcon({ html: svg, className: '', iconSize: [28, 28], iconAnchor: [14, 14] })
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
  const { meta, entities, links, grid_map, grid_cells } = useSim()

  const center = simAreaCenter(meta)
  const areaBounds = simAreaBounds(meta)

  const entityList = Object.values(entities)

  const gridRects = useMemo(() => {
    if (!grid_map.sw_lat) return []
    return Object.entries(grid_cells).map(([idx, cellState]) => {
      const style = CELL_STYLES[cellState]
      if (!style) return null
      return (
        <Rectangle
          key={idx}
          bounds={cellBounds(grid_map, Number(idx))}
          pathOptions={style}
        />
      )
    }).filter(Boolean)
  }, [grid_map, grid_cells])

  const linkLines = links.map(([idA, idB]) => {
    const a = entities[idA]
    const b = entities[idB]
    if (!a || !b) return null
    // Hide sensor-sensor and base_station-sensor links; show drone-sensor links
    if (a.entity_type === 'sensor' && b.entity_type === 'sensor') return null
    if (a.entity_type === 'base_station' && b.entity_type === 'sensor') return null
    if (a.entity_type === 'sensor' && b.entity_type === 'base_station') return null
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
        pathOptions={{ color: '#42a5f5', weight: 3, fillColor: '#90caf9', fillOpacity: 0.05, dashArray: '10 6' }}
      />
      {gridRects}
      {entityList.map((e) => {
        const idx = e.container_name?.match(/-([0-9]+)$/)?.[1] ?? e.station_id
        const label = e.entity_type === 'base_station' ? 'base station' : `${e.entity_type} #${idx}`
        const iconLabel = e.entity_type === 'base_station' ? 'B' : e.entity_type === 'drone' ? `D${idx}` : `S${idx}`
        return (
          <Marker key={e.station_id} position={[e.lat, e.lng]} icon={entityIcon(e.entity_type, iconLabel)}>
            <Popup>
              <strong>{label}</strong><br />
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
