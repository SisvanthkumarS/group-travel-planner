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
export type UpdateTripRequest = Schemas['UpdateTripRequest'];

export type Invitation = Schemas['InvitationResponse'];
export type CreateInvitationRequest = Schemas['CreateInvitationRequest'];
export type RespondInvitationRequest = Schemas['RespondInvitationRequest'];

// Shared trip chat (the private /chats routes are deprecated and not used).
export type ChatMessage = Schemas['AiChatSharedMessageResponse'];
export type ChatMessagePage = Schemas['AiChatSharedMessagePage'];
export type ChatDraft = Schemas['AiChatSharedDraftResponse'];
export type ChatDraftProposal = Schemas['CreateProposalRequest-Output'];
export type ChatReply = Schemas['AiChatSharedReply'];
export type ChatContext = Schemas['AiChatContextResponse'];
export type DraftDecision = Schemas['AiChatDraftDecisionRequest']['decision'];

export type Proposal = Schemas['ProposalResponse'];
export type ProposalStatus = Proposal['status'];
export type CreateProposalRequest = Schemas['CreateProposalRequest-Input'];

export type Poll = Schemas['PollResponse'];
export type Vote = Schemas['VoteResponse'];
export type OpenPollRequest = Schemas['OpenPollRequest'];
export type VoteRequest = Schemas['VoteRequest'];
export type ResolvePollRequest = Schemas['ResolvePollRequest'];

export type ItineraryItem = Schemas['ItineraryItemResponse'];

// Named AppNotification so it doesn't shadow the browser's Notification type.
export type AppNotification = Schemas['NotificationResponse'];
export type NotificationEventType = AppNotification['event_type'];
export type NotificationPage = Schemas['NotificationPage'];
export type NotificationPreferences = Schemas['NotificationPreferences'];
export type MarkAllReadRequest = Schemas['MarkAllReadRequest'];
export type MarkAllReadResponse = Schemas['MarkAllReadResponse'];
export type UnreadCount = Schemas['UnreadCountResponse'];
