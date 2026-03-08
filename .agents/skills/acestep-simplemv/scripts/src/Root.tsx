import React from 'react';
import {Composition, CalculateMetadataFunction} from 'remotion';
import {AudioVisualization} from './AudioVisualization';
import {MVInputProps, defaultProps} from './types';

const calculateMetadata: CalculateMetadataFunction<MVInputProps> = ({props}) => {
  const fps = 30;
  const durationInFrames = Math.ceil(props.durationInSeconds * fps);
  return {
    durationInFrames,
    fps,
    width: 1920,
    height: 1080,
  };
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="MusicVideo"
        component={AudioVisualization}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={defaultProps}
        calculateMetadata={calculateMetadata}
      />
    </>
  );
};
