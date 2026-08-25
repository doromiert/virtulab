import { BaseEdge, getStraightPath, type EdgeProps } from '@xyflow/react';
import type { CableMode } from './types';

type CableData = { mode: CableMode; color: string };

function realisticPath(sourceX: number, sourceY: number, targetX: number, targetY: number): string {
  const horizontal = Math.abs(targetX - sourceX);
  const slack = Math.max(90, horizontal * 0.12, Math.abs(targetY - sourceY) * 0.3);
  const low = Math.max(sourceY, targetY) + slack;
  return `M ${sourceX} ${sourceY} C ${sourceX} ${low}, ${targetX} ${low}, ${targetX} ${targetY}`;
}

export function CableEdge(props: EdgeProps) {
  const data = props.data as CableData | undefined;
  if (data?.mode === 'hidden') return null;
  const [straight] = getStraightPath(props);
  const path = data?.mode === 'straight'
    ? straight
    : realisticPath(props.sourceX, props.sourceY, props.targetX, props.targetY);
  return (
    <BaseEdge
      id={props.id}
      path={path}
      markerStart={props.markerStart}
      markerEnd={props.markerEnd}
      interactionWidth={18}
      style={{ stroke: data?.color ?? '#f4c430', strokeWidth: props.selected ? 7 : 5 }}
    />
  );
}
