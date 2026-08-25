import type { ConnectionLineComponentProps } from '@xyflow/react';

export function RealisticConnectionLine({ fromX, fromY, toX, toY, connectionLineStyle }: ConnectionLineComponentProps) {
  const horizontal = Math.abs(toX - fromX);
  const slack = Math.max(80, horizontal * 0.12, Math.abs(toY - fromY) * 0.3);
  const low = Math.max(fromY, toY) + slack;
  const path = `M ${fromX} ${fromY} C ${fromX} ${low}, ${toX} ${low}, ${toX} ${toY}`;
  return <path d={path} fill="none" style={connectionLineStyle} strokeLinecap="round" />;
}
