import { useEffect, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import type { TripDetail, TripMember } from '../../api/types';
import type { Viewer } from '../../lib/proposals';

export type TripContext = {
  trip: TripDetail;
  viewer: Viewer;
  memberName: (userId: number) => string;
  members: TripMember[];
};

export const useTripContext = () => useOutletContext<TripContext>();

/** Current time, refreshed every `ms` so countdowns and "can vote" stay true. */
export function useNow(ms = 30_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), ms);
    return () => window.clearInterval(id);
  }, [ms]);
  return now;
}
