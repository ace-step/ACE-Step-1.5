#!/usr/bin/env node

/**
 * CLI entry point for rendering music videos.
 * 
 * Usage:
 *   node render.mjs --audio music.mp3 --lyrics lyrics.lrc --title "Song Name" --output out/video.mp4
 *   node render.mjs --audio music.mp3 --lyrics-json lyrics.json --title "Song Name"
 * 
 * Options:
 *   --audio        Audio file path (absolute paths auto-copied to public/) or filename in public/
 *   --lyrics       Path to LRC format lyrics file
 *   --lyrics-json  Path to JSON lyrics file [{start, end, text}]
 *   --title        Main title (default: "Music Video")
 *   --subtitle     Subtitle (default: "")
 *   --credit       Bottom credit text (default: "")
 *   --duration     Audio duration in seconds (auto-detected if omitted)
 *   --offset       Lyric timing offset in seconds (default: -0.5)
 *   --output       Output file path (default: out/video.mp4)
 *   --codec        Video codec: h264, h265, vp8, vp9 (default: h264)
 */

import {execSync} from 'child_process';
import {readFileSync, readdirSync, existsSync, copyFileSync, mkdirSync} from 'fs';
import {resolve, basename, isAbsolute, join} from 'path';
import {homedir} from 'os';

/**
 * Resolve a file path that may be a MSYS2/Cygwin-style path on Windows.
 * Converts paths like /e/foo/bar to E:/foo/bar for Node.js compatibility.
 */
function resolveFilePath(p) {
  if (process.platform === 'win32' && /^\/[a-zA-Z]\//.test(p)) {
    // Convert MSYS2 path /x/... to X:/...
    return p[1].toUpperCase() + ':' + p.slice(2);
  }
  return resolve(p);
}

/**
 * Find a usable browser executable for Remotion rendering.
 *
 * Search priority:
 *   1. Environment variable BROWSER_EXECUTABLE
 *   2. CLI argument --browser
 *   3. Remotion cache (chrome-headless-shell)
 *   4. System Chrome (requires --chrome-mode=chrome-for-testing)
 *   5. System Edge (requires --chrome-mode=chrome-for-testing)
 *   6. System Chromium (requires --chrome-mode=chrome-for-testing)
 *
 * Returns {path, chromeMode} or {path: null, chromeMode: 'headless-shell'} if not found.
 *
 * chromeMode:
 *   - 'headless-shell': for chrome-headless-shell binary (uses --headless=old)
 *   - 'chrome-for-testing': for regular Chrome/Edge/Chromium (uses --headless=new)
 */
function findBrowserExecutable(cliOverride) {
  // 1. Environment variable — highest priority
  const envExe = process.env.BROWSER_EXECUTABLE;
  if (envExe && existsSync(envExe)) {
    const mode = isHeadlessShell(envExe) ? 'headless-shell' : 'chrome-for-testing';
    return {path: envExe, chromeMode: mode};
  }

  // 2. CLI argument
  if (cliOverride && existsSync(cliOverride)) {
    const mode = isHeadlessShell(cliOverride) ? 'headless-shell' : 'chrome-for-testing';
    return {path: cliOverride, chromeMode: mode};
  }

  const platform = process.platform;
  const home = homedir();

  // 3. Local node_modules/.remotion (chrome-headless-shell) — uses --headless=old
  const localCacheDir = join(process.cwd(), 'node_modules', '.remotion', 'chrome-headless-shell');
  if (existsSync(localCacheDir)) {
    try {
      // Structure: chrome-headless-shell/linux64/chrome-headless-shell-linux64/chrome-headless-shell
      const platformDir = platform === 'win32' ? 'win64' : platform === 'darwin' ? 'mac-arm64' : 'linux64';
      const exeName = platform === 'win32' ? 'chrome-headless-shell.exe' : 'chrome-headless-shell';
      const platformPath = join(localCacheDir, platformDir);

      if (existsSync(platformPath)) {
        const subdirs = readdirSync(platformPath);
        for (const subdir of subdirs) {
          const exe = join(platformPath, subdir, exeName);
          if (existsSync(exe)) return {path: exe, chromeMode: 'headless-shell'};
        }
      }
    } catch {}
  }

  // 4. User home Remotion cache (chrome-headless-shell) — uses --headless=old
  let cacheDir;
  if (platform === 'win32') {
    cacheDir = join(home, 'AppData', 'Local', 'remotion', 'chrome-headless-shell');
  } else if (platform === 'darwin') {
    cacheDir = join(home, 'Library', 'Caches', 'remotion', 'chrome-headless-shell');
  } else {
    cacheDir = join(home, '.cache', 'remotion', 'chrome-headless-shell');
  }

  if (existsSync(cacheDir)) {
    try {
      const versions = readdirSync(cacheDir).sort().reverse();
      const exeName = platform === 'win32' ? 'chrome-headless-shell.exe' : 'chrome-headless-shell';
      for (const ver of versions) {
        const exe = join(cacheDir, ver, exeName);
        if (existsSync(exe)) return {path: exe, chromeMode: 'headless-shell'};
      }
    } catch {}
  }

  // 4-6. System browsers: Chrome, Edge, Chromium — require --chrome-mode=chrome-for-testing
  const browserPaths = platform === 'win32' ? [
    // Chrome
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    // Edge (pre-installed on Windows 10/11)
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  ] : platform === 'darwin' ? [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
  ] : [
    '/usr/bin/google-chrome',
    '/usr/bin/google-chrome-stable',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    '/usr/bin/microsoft-edge',
    '/usr/bin/microsoft-edge-stable',
  ];

  for (const p of browserPaths) {
    if (existsSync(p)) return {path: p, chromeMode: 'chrome-for-testing'};
  }

  return {path: null, chromeMode: 'headless-shell'};
}

/**
 * Check if the given executable path is a chrome-headless-shell binary.
 */
function isHeadlessShell(exePath) {
  const name = exePath.toLowerCase().replace(/\\/g, '/');
  return name.includes('chrome-headless-shell');
}

function parseLrc(content) {
  const lines = content.split(/\r?\n/).filter(l => l.trim());
  const parsed = [];
  for (const line of lines) {
    const match = line.match(/^\[(\d{2}):(\d{2})(?:\.(\d{2,3}))?\]\s*(.*)$/);
    if (match) {
      const minutes = parseInt(match[1], 10);
      const seconds = parseInt(match[2], 10);
      const cs = match[3] ? parseInt(match[3].padEnd(3, '0'), 10) / 1000 : 0;
      const time = minutes * 60 + seconds + cs;
      const text = match[4].trim();
      parsed.push({time, text});
    }
  }
  const result = [];
  for (let i = 0; i < parsed.length; i++) {
    const start = parsed[i].time;
    const end = i < parsed.length - 1 ? parsed[i + 1].time : start + 5;
    if (parsed[i].text) {
      result.push({start, end, text: parsed[i].text});
    }
  }
  return result;
}

function getAudioDuration(filePath) {
  try {
    const result = execSync(
      `ffprobe -v error -show_entries format=duration -of csv=p=0 "${filePath}"`,
      {encoding: 'utf-8'}
    ).trim();
    return parseFloat(result);
  } catch {
    return null;
  }
}

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i++) {
    const key = argv[i];
    if (key.startsWith('--') && i + 1 < argv.length) {
      const name = key.slice(2);
      args[name] = argv[i + 1];
      i++;
    }
  }
  return args;
}

const args = parseArgs(process.argv);

// Validate required args
if (!args.audio) {
  console.error('Error: --audio is required');
  console.error('Usage: node render.mjs --audio music.mp3 --lyrics lyrics.lrc --title "Song"');
  process.exit(1);
}

// If audio is an absolute path, copy it into public/ and use the filename
let audioFileName = args.audio;
const resolvedAudio = resolveFilePath(args.audio);
if (isAbsolute(resolvedAudio)) {
  if (!existsSync(resolvedAudio)) {
    console.error(`Error: Audio file not found: ${resolvedAudio}`);
    process.exit(1);
  }
  const pubDir = resolve('public');
  mkdirSync(pubDir, {recursive: true});
  const fname = basename(resolvedAudio);
  const dest = resolve(pubDir, fname);
  if (resolve(resolvedAudio) !== dest) {
    copyFileSync(resolvedAudio, dest);
    console.log(`Copied audio to public/${fname}`);
  }
  audioFileName = fname;
} else {
  // Relative name — must exist in public/
  const audioPath = resolve('public', args.audio);
  if (!existsSync(audioPath)) {
    console.error(`Error: Audio file not found in public/: ${args.audio}`);
    process.exit(1);
  }
}

// Parse lyrics
let lyrics = [];
if (args.lyrics) {
  const lrcPath = resolveFilePath(args.lyrics);
  if (!existsSync(lrcPath)) {
    console.error(`Error: LRC file not found: ${lrcPath}`);
    process.exit(1);
  }
  lyrics = parseLrc(readFileSync(lrcPath, 'utf-8'));
  console.log(`Parsed ${lyrics.length} lyric lines from LRC file`);
} else if (args['lyrics-json']) {
  const jsonPath = resolveFilePath(args['lyrics-json']);
  if (!existsSync(jsonPath)) {
    console.error(`Error: JSON lyrics file not found: ${jsonPath}`);
    process.exit(1);
  }
  lyrics = JSON.parse(readFileSync(jsonPath, 'utf-8'));
  console.log(`Loaded ${lyrics.length} lyric lines from JSON file`);
}

// Determine audio duration
let duration = args.duration ? parseFloat(args.duration) : null;
if (!duration) {
  const audioPath = resolve('public', audioFileName);
  if (existsSync(audioPath)) {
    duration = getAudioDuration(audioPath);
    if (duration) {
      console.log(`Auto-detected audio duration: ${duration.toFixed(2)}s`);
    }
  }
}
if (!duration) {
  console.error('Error: Could not detect audio duration. Please provide --duration');
  process.exit(1);
}

// Build input props
// Sanitize title: single-line, max 50 chars
const rawTitle = (args.title || 'Music Video').replace(/[\r\n]+/g, ' ').trim();
const title = rawTitle.length > 50 ? rawTitle.slice(0, 47) + '...' : rawTitle;

const inputProps = {
  audioFileName: audioFileName,
  lyrics,
  title,
  subtitle: (args.subtitle || '').replace(/[\r\n]+/g, ' ').trim(),
  creditText: args.credit || '',
  durationInSeconds: duration,
  lyricOffset: args.offset ? parseFloat(args.offset) : -0.5,
};

const output = args.output ? resolveFilePath(args.output) : 'out/video.mp4';
const codec = args.codec || 'h264';

// Write props to temp file to avoid shell escaping issues
const propsFile = resolve('.render-props.json');
const {writeFileSync} = await import('fs');
writeFileSync(propsFile, JSON.stringify(inputProps));

// Find browser executable to avoid re-downloading
const {path: browserExe, chromeMode} = findBrowserExecutable(args.browser);

if (!browserExe) {
  console.warn('⚠️  No browser found. Remotion will attempt to download chrome-headless-shell from Google servers.');
  console.warn('   If download fails (e.g. Google servers inaccessible), try one of these:');
  console.warn('   1. Set environment variable: BROWSER_EXECUTABLE=/path/to/chrome-or-edge');
  console.warn('   2. Pass CLI argument: --browser /path/to/chrome-or-edge');
  console.warn('   3. Enable proxy and retry');
  console.warn('');
}

const cmd = [
  'npx remotion render',
  'MusicVideo',
  `"${output}"`,
  `--props="${propsFile}"`,
  `--codec=${codec}`,
  '--log=error',
  browserExe ? `--browser-executable="${browserExe}"` : '',
  chromeMode !== 'headless-shell' ? `--chrome-mode=${chromeMode}` : '',
].filter(Boolean).join(' ');

console.log(`\nRendering video...`);
console.log(`  Audio: ${args.audio}`);
console.log(`  Title: ${inputProps.title}`);
console.log(`  Duration: ${duration.toFixed(1)}s`);
console.log(`  Lyrics: ${lyrics.length} lines`);
console.log(`  Output: ${output}`);
console.log(`  Codec: ${codec}`);
if (browserExe) console.log(`  Browser: ${browserExe}`);
if (chromeMode !== 'headless-shell') console.log(`  Chrome mode: ${chromeMode}`);
console.log('');

try {
  const result = execSync(cmd, {encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe']});
  // Only show the final output file line (starts with '+') and size info
  const outputLines = result.split(/\r?\n/).filter(l => l.includes(output) || /^\+/.test(l.replace(/\x1b\[[0-9;]*m/g, '').trim()));
  if (outputLines.length) console.log(outputLines.join('\n'));
  console.log(`\n✅ Video rendered successfully: ${output}`);
} catch (e) {
  // Show stderr on failure for debugging
  if (e.stderr) console.error(e.stderr.toString());
  console.error('\n❌ Render failed');
  process.exit(1);
} finally {
  // Clean up temp props file
  try {
    const {unlinkSync} = await import('fs');
    unlinkSync(propsFile);
  } catch {}
}
