# Apply — Focus Studio Full Parity Restore

This patch restores the original Focus Studio experience inside the fully separated React frontend. It does **not** restore Jinja rendering or the legacy proxy.

## What is restored

### Session setup
- Task selection + workspace/priority/deadline preview
- Session outcome
- Quick sprint (25 min)
- Deep work (50 min)
- Flow block (90 min)
- Custom duration (5–180 min)
- Break length: 5 / 10 / 15 minutes
- Focus palette: Mist / Sage / Lavender / Sand
- Ambient sound choice: None / Rain / Brown / White
- Start fullscreen
- Completion chime
- Keep-screen-awake option
- Persistent Focus preferences

### Active session
- Original immersive Focus screen (sidebar/topbar hidden while a session is active)
- Countdown ring + overtime state
- Pause / Resume
- Extend by 5 minutes
- Fullscreen toggle
- Focus tools drawer
- Runtime theme switching
- Browser-generated ambient sound + volume
- Screen Wake Lock
- Park-a-thought drawer
- Convert parked thought to task
- Break overlay + break countdown
- Completion chime
- Planned-time completion sheet
- Continue overtime
- Review-session flow
- Goal result: Yes / Partly / Not yet
- Session notes
- Focus rating 1–5
- Mark linked task complete
- Save & Focus Home
- Save & Dashboard
- Exit without completing while preserving elapsed time

### Focus insights
- Weekly focused minutes
- Session count
- Average rating
- Parked-thought count
- Seven-day chart
- Time by project
- Recent completed sessions

## Architecture remains separated

```text
frontend/
  React Focus UI + browser-only focus tools
        ↓ JSON
/api/v1/focus/*
        ↓
backend/
  Focus service + persistence
```

No `legacy-proxy`, backend templates, or backend static JS are used by the active React Focus UI.

## Apply

Extract/copy this patch over the current project root:

```text
C:\Users\zelbi\OneDrive\Desktop\lifeos-ai
```

Do not run the old separation cleanup again.

## Focused verification

```powershell
cd backend
python -m pytest tests\test_api_v1_focus_native_parity.py tests\test_focus.py -v
cd ..
```

Then run the complete gate:

```powershell
.\scripts\check-react-parity.ps1
```

## Restart

Terminal 1:

```powershell
cd backend
python app.py
```

Terminal 2:

```powershell
cd frontend
npm run dev
```

Hard refresh the browser with `Ctrl + F5`, then test `/focus`.
