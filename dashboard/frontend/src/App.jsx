import MapView from './components/MapView'
import MissionPanel from './components/MissionPanel'
import { SimProvider } from './context/SimContext'
import './index.css'

export default function App() {
  return (
    <SimProvider>
      <div className="app">
        <MapView />
        <MissionPanel />
      </div>
    </SimProvider>
  )
}
