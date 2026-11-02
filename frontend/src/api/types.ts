// Friendly names for the generated OpenAPI types.
// Regenerate schema.d.ts with `pnpm run openapi:types` after backend changes.
import type { components } from './schema';

type Schemas = components['schemas'];

export type User = Schemas['UserResponse'];
export type RegisterRequest = Schemas['RegisterRequest'];
export type LoginRequest = Schemas['LoginRequest'];

export type Trip = Schemas['TripResponse'];
export type TripDetail = Schemas['TripDetailResponse'];
export type TripMember = Schemas['TripMemberResponse'];
export type CreateTripRequest = Schemas['CreateTripRequest'];

export type Invitation = Schemas['InvitationResponse'];
export type CreateInvitationRequest = Schemas['CreateInvitationRequest'];
export type RespondInvitationRequest = Schemas['RespondInvitationRequest'];

export type Proposal = Schemas['ProposalResponse'];
export type ProposalStatus = Proposal['status'];
export type CreateProposalRequest = Schemas['CreateProposalRequest'];

export type Poll = Schemas['PollResponse'];
export type Vote = Schemas['VoteResponse'];
export type OpenPollRequest = Schemas['OpenPollRequest'];
export type VoteRequest = Schemas['VoteRequest'];
export type ResolvePollRequest = Schemas['ResolvePollRequest'];

export type ItineraryItem = Schemas['ItineraryItemResponse'];
