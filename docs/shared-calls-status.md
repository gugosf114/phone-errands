# Shared conversations and calls — implementation status

Date: 2026-10-27. Production baseline: `546455ca57ecdf471107eab12538c695367c608e`.

This branch contains four requested additions. They are saved source changes awaiting local checks and live verification.

| Addition | Implementation | Remaining activation work |
|---|---|---|
| Shared phone/chat history | Vapi events, durable thread store, Claude/Codex transcript import, topic search, live chat-context delivery, managed Claude prompt hook | Check message parsing and event payloads; install and refresh managed brain; read back personal Vapi settings |
| Learning missing facts | Transcript deferrals and private questions become source-linked field requirements; account context reads them; support chat uses the same learner | Check real transcript shapes, duplicate handling, and repeat-errand context |
| Private questions | Bland tools, durable question/answer store, private Vapi delivery, phone notification fallback, direct voice and CLI answers | Check V2 tool attachment, call-ID template, tool response extraction, notification delivery, and the complete answer path |
| Takeover and AI return | Optional Twilio conference, owner ring, exact-room controls, fresh Bland leg with handover, provider webhook authentication, original time allowance | Access Twilio; select/approve a dedicated number; configure it; verify the same business leg survives both handoffs |

## Changes already made outside the checkout

Three private Bland tools were registered: `ask_george`, `get_george_answer`, and `handoff_to_george`. Their IDs are in `config/bland-tools.json`. Their bridge routes belong to this update. The deployed calling commands still use the production baseline.

## Decisions required from George

- Permission for local checks. George’s standing instruction reserves tests for his explicit choice.
- Permission for short calls between his own numbers, with a proposed total call budget of $1.
- Approval for a dedicated Twilio number if the account has no unused suitable number. Published US pricing is $1.15/month plus call use; conferencing starts at $0.0018 per participant per minute plus voice legs.

Twilio account access is being checked. A saved password exists. API credentials and an owned dedicated number have not been recovered. PG&E remains on hold.

## Activation sequence

1. Run the approved local checks and repair findings.
2. Commit the verified source and install it on the personal bridge with `scripts/install.py --apply --sync-vapi`.
3. Verify local/public revision, personal Vapi configuration, shared context, and the owner-question tools.
4. Configure the approved dedicated Twilio number with `scripts/setup-call-room.py`. Credentials stay in `/root/.twilio/voice-api.json`.
5. Run the approved call between George’s own numbers: automated greeting, private question, owner answer, human takeover, AI return, and end. Read both providers’ records for the same business connection and total charges.
6. Record the deployment receipt and actual call results in this document.

The conference route is activated by `enabled: true` in its private config. Managed calls are those carrying `ASSISTANT_JOB_ID`. Standalone calls use the direct cell handoff.

## Source projects and choices

- OpenClaw: shared voice/chat session history informed the thread store.
- TristanBrotherton/openclaw-voice-call-realtime, commit `2a2808dab102190a3ad4313d0313364fadaae999`: private owner question and late-answer delivery informed the durable question bridge.
- topness-msft/callwright, commit `f001205e6516a9c928e89a42ef3737b9c8d845a0`: learning needed details from deferrals informed `gap_learning.py`.
- agent-next/call-use, commit `e12b26eeaecf25969617b4810e5577ba96684f98`: takeover/resume with owner context informed the handover flow.

The implementation uses the existing Vapi and Bland services. Bland’s active-transfer API replaces its current AI leg with a dialed connection. Twilio supplies the persistent room, and a fresh Bland leg returns the AI with the saved context.

## Primary references

- [Bland active transfer](https://docs.bland.ai/api-v1/post/calls-active-transfer)
- [Bland V2 tools](https://docs.bland.ai/api-v2/post/tools)
- [Twilio conferences](https://www.twilio.com/docs/voice/twiml/conference)
- [Twilio US voice pricing](https://www.twilio.com/en-us/voice/pricing/us)
