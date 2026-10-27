#!/bin/bash
# phone.sh on|off|status|call|attach — the voice line.
# Rooms are opened with `voice-session`. The phone rings into the ACTIVE room (active.txt).
# Server + tunnel run inside tmux (vsrv/vtun) so they persist.
set -u
DIR=/root/.vapi/bridge
AID=9a5a14b6-7c22-46d6-a70c-a50527d41c49
FAST_AID=4346abeb-ee9e-4b7e-a8fa-57f20a32c325
CELL=+14156328008
CLAUDE=/root/.local/bin/claude
PROJ=/root/.claude/projects/-root
export PATH="$DIR/bin:$PATH"
cd "$DIR" || exit 1
debian_cmd(){ local quoted; printf -v quoted '%q ' "$@"; printf '%s' "/data/data/com.termux/files/usr/bin/proot-distro login debian -- $quoted"; }
pause(){ timeout $(( ${1:-1000}/1000 + 2 )) node -e 'setTimeout(()=>process.exit(0),'"${1:-1000}"')' 2>/dev/null; }
active_room(){ head -1 active.txt 2>/dev/null; }
room_alive(){ local r; r=$(active_room); [ -n "$r" ] && tmux has-session -t "$r" 2>/dev/null && [ "$(tmux display-message -p -t "$r" '#{pane_dead}')" = 0 ]; }

ensure_room(){
  room_alive && return 0
  # no live active room -> open a default one named 'brain' (no attach)
  local uuid name=brain; uuid=$(cat /proc/sys/kernel/random/uuid); local jsonl="$PROJ/$uuid.jsonl"
  tmux kill-session -t "$name" 2>/dev/null
  tmux new-session -d -s "$name" -x 210 -y 55 "$(debian_cmd bash -lc "cd /root && IS_SANDBOX=1 $CLAUDE --dangerously-skip-permissions --model claude-sonnet-5-5 --session-id $uuid -n $name")"
  local i
  for i in $(seq 1 40); do
    local pane; pane=$(tmux capture-pane -p -t "$name" 2>/dev/null)
    printf '%s' "$pane" | grep -q 'trust this folder' && { tmux send-keys -t "$name" Down; pause 600; tmux send-keys -t "$name" Enter; pause 1500; }
    printf '%s' "$pane" | grep -q 'bypass permissions on' && break
    pause 1000
  done
  printf '%s\n%s\n' "$name" "$jsonl" > active.txt
  touch rooms.txt; grep -v -P "^$name\t" rooms.txt > rooms.txt.tmp 2>/dev/null; mv rooms.txt.tmp rooms.txt
  printf '%s\t%s\n' "$name" "$jsonl" >> rooms.txt
  echo "opened default room 'brain'"
}
server_up(){ python3 "$DIR/service.py" healthy >/dev/null 2>&1; }
start_server(){ server_up && return 0; python3 "$DIR/service.py" stop || return 1; tmux kill-session -t vsrv 2>/dev/null; tmux new-session -d -s vsrv "$(debian_cmd bash -lc "cd $DIR && exec env PERSONAL_ASSISTANT_BRIDGE=1 node server_tmux.js > server.log 2>&1")"; local i; for i in $(seq 1 10); do server_up && return 0; pause 800; done; return 1; }
start_tunnel(){
  # fixed address: ngrok dev domain (token in /root/.config/ngrok/ngrok.yml, domain in ngrok_domain.txt). Never changes.
  local dom url; dom=$(cat "$DIR/ngrok_domain.txt" 2>/dev/null); url="https://$dom"
  if tmux has-session -t vtun 2>/dev/null && [ "$(curl -s -m 8 -o /dev/null -w '%{http_code}' "$url/")" = 200 ]; then echo "$url"; return 0; fi
  tmux kill-session -t vtun 2>/dev/null; : > "$DIR/tunnel.log"
  tmux new-session -d -s vtun "$(debian_cmd bash -lc "ngrok http 8790 --url=$dom --log=stdout > $DIR/tunnel.log 2>&1")"
  local i; for i in $(seq 1 30); do [ "$(curl -s -m 5 -o /dev/null -w '%{http_code}' "$url/")" = 200 ] && { echo "$url"; return 0; }; pause 1000; done
  return 1
}
point_vapi(){ local url="${1%/}" key fast lk code
  key=$(grep '^VAPI_KEY=' /root/.gmail/aicalls.env | cut -d= -f2- | tr -d '"')
  # old brain line (custom-LLM): whole turn through the brain
  code=$(curl -s -m 30 -o /dev/null -w '%{http_code}' -X PATCH -H "Authorization: Bearer $key" -H "Content-Type: application/json" \
    -d "{\"model\":{\"provider\":\"custom-llm\",\"model\":\"claude-sonnet-5-5\",\"url\":\"$url/chat/completions\"}}" "https://api.vapi.ai/assistant/$AID")
  [ "$code" = 200 ] && echo "vapi brain line -> $url/chat/completions" || echo "vapi brain line re-point FAILED ($code)"
  # fast line (Sonnet 5 inside Vapi): only its tools point here
  fast="$FAST_AID"; lk=$(cut -d= -f2 /root/.vapi/bridge/line.key 2>/dev/null)
  [ -z "$fast" ] && return 0
  code=$(python3 -I - "$fast" "$url/tools" "$lk" "$key" <<'PY'
import sys,json,urllib.request
fid,turl,lk,key=sys.argv[1:5]; H={"Authorization":"Bearer "+key,"Content-Type":"application/json","User-Agent":"curl/8.5.0"}
g=json.load(urllib.request.urlopen(urllib.request.Request("https://api.vapi.ai/assistant/"+fid,headers=H),timeout=30))
tools=g["model"].get("tools",[])
for t in tools: t["server"]={"url":turl,"timeoutSeconds":t.get("server",{}).get("timeoutSeconds",15),"headers":{"X-Line-Key":lk}}
m=g["model"]; m["tools"]=tools
try:
    urllib.request.urlopen(urllib.request.Request("https://api.vapi.ai/assistant/"+fid,data=json.dumps({"model":m}).encode(),headers=H,method="PATCH"),timeout=30); print(200)
except urllib.error.HTTPError as e: print(e.code)
PY
)
  [ "$code" = 200 ] && echo "vapi fast line tools -> $url/tools" || echo "vapi fast line re-point FAILED ($code)"
}
case "${1:-status}" in
  on)
    touch /root/.vapi/bridge/WANTED
    ensure_room
    start_server && echo "server: up" || { echo "server failed"; exit 1; }
    URL=$(start_tunnel) || { echo "tunnel failed (see tunnel.log)"; exit 1; }
    echo "tunnel: $URL"
    pause 3000
    code=$(curl -s -m8 -o /dev/null -w '%{http_code}' "$URL/" 2>/dev/null); echo "public door: $code"
    point_vapi "$URL"
    echo "LINE ON. Active room: $(active_room). Call 650-252-3543.  Watch/type: bash /root/.vapi/bridge/phone.sh attach"
    ;;
  use)
    # phone.sh use fast|brain  -> which assistant answers 650-252-3543
    key=$(grep '^VAPI_KEY=' /root/.gmail/aicalls.env | cut -d= -f2- | tr -d '"')
    case "$2" in fast) want="$FAST_AID";; brain) want="$AID";; *) echo "usage: phone.sh use fast|brain"; exit 1;; esac
    code=$(curl -s -m 30 -o /dev/null -w '%{http_code}' -X PATCH -H "Authorization: Bearer $key" -H "Content-Type: application/json" -d "{\"assistantId\":\"$want\"}" "https://api.vapi.ai/phone-number/4077477e-40b4-4974-8e43-ad5ff10511fc")
    [ "$code" = 200 ] && echo "650-252-3543 now answers with: $2 ($want)" || echo "flip FAILED ($code)"
    ;;
  keeper)
    tmux kill-session -t vkeep 2>/dev/null
    tmux new-session -d -s vkeep "$(debian_cmd bash -lc "while true; do bash $DIR/phone.sh ensure >> $DIR/keeper.log 2>&1; sleep 300; done")"
    echo "keeper on (tmux session vkeep, checks every 5 min, log keeper.log)"
    ;;
  which)
    key=$(grep '^VAPI_KEY=' /root/.gmail/aicalls.env | cut -d= -f2- | tr -d '"')
    cur=$(curl -s -m 30 -H "Authorization: Bearer $key" "https://api.vapi.ai/phone-number/4077477e-40b4-4974-8e43-ad5ff10511fc" | python3 -I -c "import sys,json; print(json.load(sys.stdin).get('assistantId'))")
    fast="$FAST_AID"
    if [ "$cur" = "$fast" ]; then echo "650-252-3543 -> fast line (Sonnet 5 in Vapi + brain tools)"; elif [ "$cur" = "$AID" ]; then echo "650-252-3543 -> brain line (all turns through the tmux session)"; else echo "650-252-3543 -> $cur"; fi
    ;;
  call) python3 "$DIR/place_call.py" --assistant "$AID" --to "$CELL" ;;
  attach) exec tmux attach -t "$(active_room)" ;;
  off) python3 "$DIR/service.py" stop || exit 1; rm -f /root/.vapi/bridge/WANTED; tmux kill-session -t vsrv 2>/dev/null; tmux kill-session -t vtun 2>/dev/null; echo "LINE OFF (rooms left open; auto-return disabled)";;
  restart)
    python3 "$DIR/service.py" stop || exit 1
    tmux kill-session -t vsrv 2>/dev/null
    start_server || exit 1
    echo "personal bridge restarted"
    ;;
  status)
    echo "active room: $(active_room)  ($(room_alive && echo up || echo gone))"
    server_up && echo "server: up" || echo "server: down"
    (tmux has-session -t vtun 2>/dev/null) && echo "tunnel: up (https://$(cat $DIR/ngrok_domain.txt) door $(curl -s -m 8 -o /dev/null -w '%{http_code}' https://$(cat $DIR/ngrok_domain.txt)/))" || echo "tunnel: down"
    ;;
  ensure)
    [ -f "$DIR/MAINTENANCE" ] && { echo maintenance; exit 0; }
    [ -f "$DIR/WANTED" ] || { echo off; exit 0; }
    if room_alive && server_up && tmux has-session -t vtun 2>/dev/null; then echo ok; exit 0; fi
    ensure_room >/dev/null 2>&1; start_server >/dev/null 2>&1
    URL=$(start_tunnel 2>/dev/null) && point_vapi "$URL" >/dev/null 2>&1
    if room_alive && server_up && tmux has-session -t vtun 2>/dev/null; then echo ok; else echo "ensure: bringing up"; fi
    ;;
  *) echo "usage: phone.sh on|off|status|restart|keeper|use fast|brain|which|call|attach|ensure  ; open rooms with: voice-session [name]";;
esac
