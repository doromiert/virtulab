import { FileText, Inbox } from 'lucide-react';
import type { NodeProps } from '@xyflow/react';
import type { PrintDocument } from './types';

export type PrintDocumentNodeData = { document: PrintDocument; onStore: (document: PrintDocument) => void };

export function PrintDocumentNode({ data, selected }: NodeProps) {
  const { document, onStore } = data as PrintDocumentNodeData;
  return (
    <article className={`print-document-node ${selected ? 'is-selected' : ''}`}>
      <div className="document-paper"><FileText /><span><strong>{document.name}</strong><small>{document.pages} str.</small></span></div>
      <button className="nodrag icon-button" title="Przenieś do odbiornika" onClick={() => onStore(document)}><Inbox /></button>
    </article>
  );
}
