#!/usr/bin/env python3
# Fires an outbound Vapi call. Lives here so it survives scratchpad wipes.
# The assistants themselves live on Vapi's servers; this just dials one.
#
# Usage:
#   python3 /root/.vapi/place_call.py --assistant <id> --to +1XXXXXXXXXX \
#       --task "what to do on the call" [--first "opening line"] [--from <phoneNumberId>]
#
# --from defaults to the 650 line's phoneNumberId.
import argparse, json, sys, urllib.request, urllib.error

ENV_PATH = "/root/.gmail/aicalls.env"
DEFAULT_FROM = "4077477e-40b4-4974-8e43-ad5ff10511fc"  # +16502523543


def load_env(p):
    return dict(
        l.strip().split("=", 1)
        for l in open(p)
        if "=" in l and not l.strip().startswith("#")
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--assistant", required=True)
    ap.add_argument("--to", required=True)
    ap.add_argument("--task", default="")
    ap.add_argument("--first", default=None)
    ap.add_argument("--from", dest="frm", default=DEFAULT_FROM)
    a = ap.parse_args()
    if a.assistant not in {'4346abeb-ee9e-4b7e-a8fa-57f20a32c325', '9a5a14b6-7c22-46d6-a70c-a50527d41c49'} or a.frm != DEFAULT_FROM:
        ap.error('Use the personal assistant and personal phone number.')

    env = load_env(ENV_PATH)
    H = {
        "Authorization": "Bearer " + env["VAPI_KEY"].strip().strip('"').strip("'"),
        "Content-Type": "application/json",
        "User-Agent": "curl/8",   # Cloudflare 1010 guard
        "Accept": "application/json",
    }
    overrides = {}
    if a.task:
        overrides["variableValues"] = {"task": a.task}
    if a.first:
        overrides["firstMessage"] = a.first

    body = {"phoneNumberId": a.frm, "assistantId": a.assistant,
            "customer": {"number": a.to}}
    if overrides:
        body["assistantOverrides"] = overrides

    req = urllib.request.Request(
        "https://api.vapi.ai/call", data=json.dumps(body).encode(),
        headers=H, method="POST",
    )
    try:
        r = json.load(urllib.request.urlopen(req, timeout=40))
        print("CALL id:", r.get("id"), "| status:", r.get("status"))
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, e.read().decode()[:500])
        sys.exit(1)


if __name__ == "__main__":
    main()
