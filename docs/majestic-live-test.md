# Majestic George phone test

The personal bridge serves the original Piper voice model through Vapi's custom
speech interface. `POST /majestic/tts` accepts a `voice-request` and streams raw
mono, signed 16-bit little-endian PCM at the requested sample rate.
`GET /majestic/health` starts and checks the speech helper. Both require the
existing `X-Line-Key` bridge header.

The helper loads the model once and uses the saved model configuration and
`SynthesisConfig()` defaults, matching the original local renderer. It runs on
loopback port 8793 and exits when its parent bridge exits. The model and its
configuration remain unchanged.

The first test uses a separate Vapi assistant and a free inbound test number.
The existing Bland caller rings George, then transfers that call to the Vapi
number. This uses Bland's existing call balance and avoids buying an outbound
number. The original Ava personal assistant and bakery assistants keep their
existing configuration.

The baseline test has background sound off and no added filler instructions.
George judges the sound, response delay, interruptions, and sentence endings.
Test assistant IDs, phone number IDs, provider call IDs, and actual transcripts
belong in the private application case record.

Provider references:

- https://docs.vapi.ai/customization/custom-voices/custom-tts
- https://docs.vapi.ai/calls/outbound-calling
- https://docs.bland.ai/api-v1/post/calls
