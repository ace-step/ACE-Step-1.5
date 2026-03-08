export type AdapterLibraryKind = 'lora' | 'lokr' | 'lycoris' | 'unknown'

export interface AdapterLibraryEntry {
  name: string
  path: string
  directory: string
  kind: AdapterLibraryKind
  modified_at: number | null
}

export interface LoraRuntimeStatus {
  lora_loaded: boolean
  use_lora: boolean
  lora_scale: number
  adapter_type?: string | null
  scales: Record<string, number>
  active_adapter: string | null
  adapters: string[]
  synthetic_default_mode?: boolean
}
