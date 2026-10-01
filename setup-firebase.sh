#!/bin/bash
# One-time Firebase setup for the GitHub Pages build (Friends + cross-device sync).
# Needs `firebase login` first. Creates the project, a web app, the Firestore database and its rules,
# then writes firebase-config.json (public by design; security comes from firestore.rules).
set -euo pipefail
cd "$(dirname "$0")"
PROJECT="${1:-pulpit-index-sk17}"
LOCATION="${2:-europe-west4}"

if ! firebase projects:list --json | python3 -c "import sys,json; ids=[p['projectId'] for p in json.load(sys.stdin).get('result',[])]; sys.exit(0 if '$PROJECT' in ids else 1)"; then
  firebase projects:addfirebase "$PROJECT" 2>/dev/null || firebase projects:create "$PROJECT" --display-name "Pulpit Index"
fi

APP_ID=$(firebase apps:list WEB --project "$PROJECT" --json | python3 -c "import sys,json; r=json.load(sys.stdin).get('result',[]); print(r[0]['appId'] if r else '')")
if [ -z "$APP_ID" ]; then
  APP_ID=$(firebase apps:create WEB "Pulpit Index" --project "$PROJECT" --json | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['appId'])")
fi
firebase apps:sdkconfig WEB "$APP_ID" --project "$PROJECT" --json \
  | python3 -c "import sys,json; c=json.load(sys.stdin)['result']; c=c.get('sdkConfig',c); json.dump({k:c[k] for k in ['apiKey','authDomain','projectId','storageBucket','messagingSenderId','appId'] if k in c}, open('firebase-config.json','w'), indent=1)"

firebase firestore:databases:list --project "$PROJECT" --json | grep -q '(default)' \
  || firebase firestore:databases:create "(default)" --location "$LOCATION" --project "$PROJECT"

[ -f firebase.json ] || echo '{ "firestore": { "rules": "firestore.rules" } }' > firebase.json
firebase deploy --only firestore:rules --project "$PROJECT"

echo
echo "Done: firebase-config.json written for $PROJECT."
echo "Still needed in the Firebase console (two clicks):"
echo "  1. https://console.firebase.google.com/project/$PROJECT/authentication/providers  -> Google -> Enable -> Save"
echo "  2. https://console.firebase.google.com/project/$PROJECT/authentication/settings   -> Authorized domains -> Add domain: sagek17.github.io"
