import {LyricLine} from './types';

/**
 * Parse LRC format lyrics into LyricLine array.
 * LRC format: [mm:ss.xx] lyrics text
 * 
 * Example:
 *   [00:02.99] Version one point five is here today
 *   [00:07.00] ACE-Step's rising, leading the way
 */
export function parseLrc(lrcContent: string): LyricLine[] {
  const lines = lrcContent.split('\n').filter((line) => line.trim());
  const parsed: {time: number; text: string}[] = [];

  for (const line of lines) {
    // Match [mm:ss.xx] or [mm:ss] format
    const match = line.match(/^\[(\d{2}):(\d{2})(?:\.(\d{2,3}))?\]\s*(.*)$/);
    if (match) {
      const minutes = parseInt(match[1], 10);
      const seconds = parseInt(match[2], 10);
      const centiseconds = match[3] ? parseInt(match[3].padEnd(3, '0'), 10) / 1000 : 0;
      const time = minutes * 60 + seconds + centiseconds;
      const text = match[4].trim();
      parsed.push({time, text});
    }
  }

  // Convert to LyricLine with start/end
  const result: LyricLine[] = [];
  for (let i = 0; i < parsed.length; i++) {
    const start = parsed[i].time;
    const end = i < parsed.length - 1 ? parsed[i + 1].time : start + 5;
    const text = parsed[i].text;
    if (text) {
      result.push({start, end, text});
    }
  }

  return result;
}
