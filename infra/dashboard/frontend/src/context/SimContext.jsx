import { createContext, useContext, useEffect, useReducer } from 'react'

const WS_URL = `ws://${window.location.hostname}:8000/ws`
export const API_URL = `http://${window.location.hostname}:8000`

const initialState = { meta: {}, entities: {}, links: [], grid_map: {}, grid_cells: {}, tick: 0 }

function reducer(state, action) {
  if (action.type === 'update') return { ...state, ...action.payload }
  return state
}

const SimContext = createContext(initialState)

export function SimProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, initialState)

  useEffect(() => {
    let ws
    let cancelled = false

    function connect() {
      ws = new WebSocket(WS_URL)
      ws.onmessage = (e) => dispatch({ type: 'update', payload: JSON.parse(e.data) })
      ws.onclose = () => { if (!cancelled) setTimeout(connect, 2000) }
    }

    connect()
    return () => { cancelled = true; ws?.close() }
  }, [])

  return <SimContext.Provider value={state}>{children}</SimContext.Provider>
}

export function useSim() {
  return useContext(SimContext)
}
