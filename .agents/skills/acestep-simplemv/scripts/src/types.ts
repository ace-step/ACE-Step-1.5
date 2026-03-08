export interface LyricLine {
  start: number;
  end: number;
  text: string;
}

export interface MVInputProps extends Record<string, unknown> {
  /** Path to audio file (relative to public/ or absolute URL) */
  audioFileName: string;
  /** Lyrics as JSON array [{start, end, text}] */
  lyrics: LyricLine[];
  /** Main title displayed at top */
  title: string;
  /** Subtitle displayed below title */
  subtitle: string;
  /** Bottom credit text */
  creditText: string;
  /** Audio duration in seconds (used to calculate total frames) */
  durationInSeconds: number;
  /** Lyric timing offset in seconds (positive = delay, negative = advance) */
  lyricOffset: number;
}

export const defaultProps: MVInputProps = {
  audioFileName: 'celebration.mp3',
  lyrics: [],
  title: 'ACE-Step',
  subtitle: 'v1.5',
  creditText: 'Powered by Claude Code + ACE-Step',
  durationInSeconds: 150,
  lyricOffset: -0.5,
};
