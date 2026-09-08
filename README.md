# phone-errands — the app that phones for George

Two small tools. They live on George's phone box at `/usr/local/bin`. This repo is the copy of record.

- **phone-ask** — calls a place and asks up to 4 plain questions. Brings the answers back.
  `phone-ask "+14155551234" "Ace Hardware on Mission" "Are you open Sunday?" "Do you sell propane?"`
- **phone-do** — runs an errand from a card: who to call, the goal, the facts, the limits.
  `phone-do errands/example-late-fee.txt` (`--dry` shows the plan, places no call)

The robot says it is George's assistant, calling on his behalf. It never says it is George. It never states a fact that is not on the card. It never agrees to money that is not in the goal. If asked whether it is a robot, it says yes.

Phone line and voice: Bland (app.bland.ai), account gugosf@gmail.com, key at `/root/.bland/key` on the box (never in this repo). About 14 cents a minute. Balance: `phone-ask --balance`.

Records: every call's card, answers, and full transcript are saved on the box under `/root/.bland/calls/` and `/root/.bland/errands/`. `phone-do --last` prints the last one.

Errand card format: see `errands/example-late-fee.txt`.
