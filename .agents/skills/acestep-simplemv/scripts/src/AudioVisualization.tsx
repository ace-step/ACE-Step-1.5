import React from 'react';
import {
  AbsoluteFill,
  Audio,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  Easing,
  staticFile,
} from 'remotion';
import {useAudioData, visualizeAudio} from '@remotion/media-utils';
import {MVInputProps} from './types';

export const AudioVisualization: React.FC<MVInputProps> = ({
  audioFileName,
  lyrics,
  title,
  subtitle,
  creditText,
  lyricOffset,
}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();

  const audioSrc = audioFileName.startsWith('http')
    ? audioFileName
    : staticFile(audioFileName);

  const audioData = useAudioData(audioSrc);

  if (!audioData) {
    return null;
  }

  const visualization = visualizeAudio({
    fps,
    frame,
    audioData,
    numberOfSamples: 128,
    optimizeFor: 'speed',
  });

  const currentTime = frame / fps + lyricOffset;

  const currentLyric = lyrics.find(
    (lyric) => currentTime >= lyric.start && currentTime < lyric.end
  );

  const lyricProgress = currentLyric
    ? interpolate(
        currentTime,
        [currentLyric.start, currentLyric.start + 0.3],
        [0, 1],
        {extrapolateRight: 'clamp'}
      )
    : 0;

  const titleOpacity = interpolate(frame, [0, 30], [0, 1], {
    extrapolateRight: 'clamp',
  });

  const titleY = interpolate(frame, [0, 30], [-50, 0], {
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.ease),
  });

  const hue = interpolate(frame, [0, durationInFrames], [200, 320], {
    extrapolateRight: 'wrap',
  });

  const avgAmplitude =
    visualization.reduce((sum, val) => sum + val, 0) / visualization.length;

  return (
    <AbsoluteFill>
      {/* Animated gradient background */}
      <AbsoluteFill
        style={{
          background: `linear-gradient(135deg, hsl(${hue}, 80%, 12%) 0%, hsl(${hue + 80}, 70%, 8%) 100%)`,
        }}
      />

      {/* Radial glow effect */}
      <AbsoluteFill
        style={{
          background: `radial-gradient(circle at 50% 50%, hsla(${hue}, 100%, 50%, ${avgAmplitude * 0.3}) 0%, transparent 50%)`,
        }}
      />

      {/* Audio source */}
      <Audio src={audioSrc} />

      {/* Bottom frequency bars */}
      <AbsoluteFill
        style={{
          justifyContent: 'flex-end',
          alignItems: 'center',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-end',
            justifyContent: 'center',
            gap: 4,
            height: 350,
            width: '90%',
            marginBottom: 180,
          }}
        >
          {visualization.map((value, index) => {
            const scaledValue = Math.pow(value, 0.6);
            const barHeight = Math.max(scaledValue * 800, 20);
            const colorIndex = (index / visualization.length) * 360;

            return (
              <div
                key={index}
                style={{
                  width: `${100 / visualization.length}%`,
                  height: barHeight,
                  background: `linear-gradient(to top,
                    hsl(${(colorIndex + hue) % 360}, 90%, 60%),
                    hsl(${(colorIndex + hue + 40) % 360}, 90%, 70%))`,
                  borderRadius: '4px 4px 0 0',
                  boxShadow: `0 0 ${10 + scaledValue * 30}px hsla(${(colorIndex + hue) % 360}, 100%, 60%, ${scaledValue})`,
                  transition: 'height 0.05s ease-out',
                }}
              />
            );
          })}
        </div>
      </AbsoluteFill>

      {/* Symmetrical side bars */}
      <AbsoluteFill
        style={{
          justifyContent: 'center',
          alignItems: 'center',
        }}
      >
        {/* Left bars */}
        <div
          style={{
            position: 'absolute',
            left: 40,
            display: 'flex',
            flexDirection: 'column',
            gap: 8,
            height: '80%',
            justifyContent: 'space-around',
          }}
        >
          {visualization.slice(0, 20).map((value, index) => {
            const scaledValue = Math.pow(value, 0.6);
            const barWidth = Math.max(scaledValue * 300, 10);
            const colorIndex = (index / 20) * 360;
            return (
              <div
                key={index}
                style={{
                  width: barWidth,
                  height: 12,
                  background: `linear-gradient(to right,
                    hsl(${(colorIndex + hue) % 360}, 90%, 60%),
                    hsl(${(colorIndex + hue + 40) % 360}, 90%, 70%))`,
                  borderRadius: '0 6px 6px 0',
                  boxShadow: `0 0 ${10 + scaledValue * 20}px hsla(${(colorIndex + hue) % 360}, 100%, 60%, ${scaledValue})`,
                }}
              />
            );
          })}
        </div>

        {/* Right bars */}
        <div
          style={{
            position: 'absolute',
            right: 40,
            display: 'flex',
            flexDirection: 'column',
            gap: 8,
            height: '80%',
            justifyContent: 'space-around',
            alignItems: 'flex-end',
          }}
        >
          {visualization.slice(0, 20).map((value, index) => {
            const scaledValue = Math.pow(value, 0.6);
            const barWidth = Math.max(scaledValue * 300, 10);
            const colorIndex = (index / 20) * 360;
            return (
              <div
                key={index}
                style={{
                  width: barWidth,
                  height: 12,
                  background: `linear-gradient(to left,
                    hsl(${(colorIndex + hue + 180) % 360}, 90%, 60%),
                    hsl(${(colorIndex + hue + 220) % 360}, 90%, 70%))`,
                  borderRadius: '6px 0 0 6px',
                  boxShadow: `0 0 ${10 + scaledValue * 20}px hsla(${(colorIndex + hue + 180) % 360}, 100%, 60%, ${scaledValue})`,
                }}
              />
            );
          })}
        </div>
      </AbsoluteFill>

      {/* Center title area */}
      <AbsoluteFill
        style={{
          justifyContent: 'flex-start',
          alignItems: 'center',
          paddingTop: 60,
        }}
      >
        <div
          style={{
            textAlign: 'center',
            transform: `scale(${1 + avgAmplitude * 0.1})`,
            transition: 'transform 0.1s ease-out',
          }}
        >
          <div
            style={{
              fontSize: 96,
              fontWeight: 'bold',
              color: 'white',
              opacity: titleOpacity,
              transform: `translateY(${titleY}px)`,
              textShadow: `0 0 40px hsla(${hue}, 100%, 70%, 0.8), 0 4px 20px rgba(0,0,0,0.5)`,
              fontFamily: '"Noto Sans CJK JP", "Noto Sans CJK SC", Arial, sans-serif',
              marginBottom: 10,
            }}
          >
            {title}
          </div>
          <div
            style={{
              fontSize: 56,
              fontWeight: '600',
              color: 'rgba(255,255,255,0.95)',
              opacity: titleOpacity,
              transform: `translateY(${titleY}px)`,
              textShadow: `0 0 30px hsla(${hue + 60}, 100%, 70%, 0.6), 0 2px 10px rgba(0,0,0,0.5)`,
              fontFamily: '"Noto Sans CJK JP", "Noto Sans CJK SC", Arial, sans-serif',
              letterSpacing: '4px',
            }}
          >
            {subtitle}
          </div>
        </div>
      </AbsoluteFill>

      {/* Lyrics display */}
      {currentLyric && currentLyric.text && (
        <AbsoluteFill
          style={{
            justifyContent: 'center',
            alignItems: 'center',
            paddingTop: 100,
          }}
        >
          <div
            style={{
              fontSize: 48,
              fontWeight: '600',
              color: 'white',
              textAlign: 'center',
              maxWidth: '85%',
              opacity: lyricProgress,
              transform: `translateY(${(1 - lyricProgress) * 30}px)`,
              textShadow: `0 0 40px hsla(${hue}, 100%, 70%, 0.8), 0 4px 30px rgba(0,0,0,0.9)`,
              fontFamily: '"Noto Sans CJK JP", "Noto Sans CJK SC", Arial, sans-serif',
              lineHeight: 1.5,
              padding: '25px 50px',
              background: `linear-gradient(135deg, rgba(0,0,0,0.4), rgba(0,0,0,0.2))`,
              backdropFilter: 'blur(15px)',
              borderRadius: '20px',
              border: `2px solid hsla(${hue}, 80%, 60%, 0.3)`,
              boxShadow: `0 8px 32px rgba(0,0,0,0.5), inset 0 0 40px hsla(${hue}, 100%, 50%, 0.1)`,
            }}
          >
            {currentLyric.text}
          </div>
        </AbsoluteFill>
      )}

      {/* Bottom credit text */}
      <AbsoluteFill
        style={{
          justifyContent: 'flex-end',
          alignItems: 'center',
          padding: 50,
        }}
      >
        <div
          style={{
            fontSize: 32,
            fontWeight: '500',
            color: 'white',
            opacity: 0.8,
            textAlign: 'center',
            textShadow: `0 0 20px hsla(${hue}, 100%, 70%, 0.6), 0 2px 10px rgba(0,0,0,0.7)`,
            fontFamily: '"Noto Sans CJK JP", "Noto Sans CJK SC", Arial, sans-serif',
          }}
        >
          {creditText}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
