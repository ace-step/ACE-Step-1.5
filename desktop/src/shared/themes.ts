export interface ThemeDefinition {
  bgPrimary: string
  bgSecondary: string
  bgInput: string
  textPrimary: string
  textMuted: string
  textDim: string
  violet: string
  cyan: string
}

export interface ThemeRecord {
  id: string
  name: string
  theme_json: ThemeDefinition
  is_builtin: number
  created_at: number
  updated_at: number | null
}

export interface CreateThemeInput {
  name: string
  definition: ThemeDefinition
}

export interface BuiltInTheme {
  id: string
  name: string
  definition: ThemeDefinition
}

export const BUILTIN_THEMES: BuiltInTheme[] = [
  {
    id: 'midnight-lattice',
    name: 'Midnight Lattice',
    definition: {
      bgPrimary: '#0a0a0f',
      bgSecondary: '#111118',
      bgInput: '#0d0d14',
      textPrimary: '#e2e8f0',
      textMuted: '#94a3b8',
      textDim: '#64748b',
      violet: '#7c3aed',
      cyan: '#06b6d4'
    }
  },
  {
    id: 'tape-sunset',
    name: 'Tape Sunset',
    definition: {
      bgPrimary: '#16121c',
      bgSecondary: '#221a28',
      bgInput: '#110d16',
      textPrimary: '#f6eee7',
      textMuted: '#d8b8a7',
      textDim: '#9c7a6c',
      violet: '#ff7a59',
      cyan: '#ffd166'
    }
  },
  {
    id: 'sea-glass',
    name: 'Sea Glass',
    definition: {
      bgPrimary: '#091419',
      bgSecondary: '#112129',
      bgInput: '#0c171c',
      textPrimary: '#e8fffa',
      textMuted: '#a4d3cb',
      textDim: '#6d948d',
      violet: '#2dd4bf',
      cyan: '#7dd3fc'
    }
  }
]
