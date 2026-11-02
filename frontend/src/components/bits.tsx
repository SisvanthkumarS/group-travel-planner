// Small presentational pieces shared across screens.
import type { ProposalStatus } from '../api/types';
import { initials } from '../auth/session';
import { STATUS_LABEL } from '../lib/proposals';

const CHIP_CLASS: Record<ProposalStatus, string> = {
  PENDING: 'chip--muted',
  OPEN: 'chip--blue',
  TIED: 'chip--warm',
  APPROVED: 'chip--ok',
  REJECTED: 'chip--grey',
  WITHDRAWN: 'chip--dashed',
  CANCELLED: 'chip--dashed',
};

export function StatusChip({ status }: { status: ProposalStatus }) {
  return (
    <span className={`chip ${CHIP_CLASS[status]}`}>{STATUS_LABEL[status]}</span>
  );
}

export function RoleChip({ organizer }: { organizer: boolean }) {
  return (
    <span className={`chip ${organizer ? 'chip--blue' : 'chip--muted'}`}>
      {organizer ? 'Organizer' : 'Member'}
    </span>
  );
}

const AVATAR_TINTS = [
  '#F08A4B',
  '#A9C1FF',
  '#9FDCC8',
  '#F4C6D7',
  '#FCE3A6',
  '#E3E8EF',
  '#C9B8F5',
  '#B8E3F5',
];

export function Avatar({
  name,
  userId,
  size = 32,
}: {
  name: string;
  userId: number;
  size?: number;
}) {
  return (
    <span
      className="avatar avatar--tint"
      style={{
        width: size,
        height: size,
        background: AVATAR_TINTS[userId % AVATAR_TINTS.length],
      }}
      aria-hidden="true"
    >
      {initials(name)}
    </span>
  );
}

/** Yes/no bar. Width is share of eligible voters so "not voted yet" shows as empty track. */
export function VoteBar({
  yes,
  no,
  eligible,
}: {
  yes: number;
  no: number;
  eligible: number;
}) {
  const total = Math.max(eligible, yes + no, 1);
  return (
    <div
      className="vote-bar"
      role="img"
      aria-label={`${yes} yes, ${no} no, ${eligible - yes - no} not voted`}
    >
      <span
        className="vote-bar__yes"
        style={{ width: `${(yes / total) * 100}%` }}
      />
      <span
        className="vote-bar__no"
        style={{ width: `${(no / total) * 100}%` }}
      />
    </div>
  );
}

export function PlusIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

export function CheckIcon({ size = 16 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M5 12l5 5L19 7" />
    </svg>
  );
}

export function BackIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M15 6l-6 6 6 6" />
    </svg>
  );
}

export function QueryError({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry?: () => void;
}) {
  const message =
    error instanceof Error ? error.message : 'Something went wrong.';
  return (
    <div className="form-error" role="alert">
      {message}{' '}
      {onRetry && (
        <button type="button" className="link-btn" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}
