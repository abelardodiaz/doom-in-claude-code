/** Una corrida de celdas iguales: [cuantas, color de arriba, color de abajo]. */
export type Corrida = [number, string, string]

export type InfoJev = {
  ms: number
  probs: Record<string, number>
  probs_meta: Record<string, number>
  meta: string | null
  peligro: number
  llamadas: number
  dudas: number
  errores: number
  ultimo_error: string
}

export type Frame = {
  n: number
  filas: Corrida[][]
  modo: string
  orden: string
  estado: string
  piloto: 'jev' | 'claude'
  jev: InfoJev | null
  mapa?: string
  niveles?: number
  meta?: string | null
  plan?: string[]
  resumen_mapa?: string
}

declare module 'claude-code' {
  interface PluginState {
    'doom-pane': {
      frame: Frame | null
      bitacora: string[]
      activo: boolean
    }
  }
}
