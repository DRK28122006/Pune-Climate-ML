import type { ReactNode } from 'react';
import { EmptyState, ErrorState, LoadingState } from './ui';

interface Props<T> {
  state: { status: 'loading' | 'error' | 'ready'; data: T | null; error: string | null; reload: () => void };
  children: (data: T) => ReactNode;
  isEmpty?: (data: T) => boolean;
}

/** Shows loading, error and empty states around any async data. */
export default function DataGate<T>({ state, children, isEmpty }: Props<T>) {
  if (state.status === 'loading') return <LoadingState />;
  if (state.status === 'error') return <ErrorState message={state.error ?? 'Unknown error'} onRetry={state.reload} />;
  if (state.data === null || (isEmpty && isEmpty(state.data)))
    return <EmptyState title="No data available" text="There is nothing to show for this view yet." />;
  return <>{children(state.data)}</>;
}
