# Triathlon Periodization Guide

## Phase Definitions

### Base Phase
- **Goal**: Build aerobic foundation, movement efficiency, structural resilience.
- **Duration**: 8–12 weeks (longer for beginners).
- **Intensity**: Predominantly Zone 2 (≥80% of volume). No high-intensity intervals.
- **Load**: Start at ~70% of target peak weekly hours. Build 5–8% per week.
- **Key sessions**: Long slow swims, steady-state bike rides, conversational-pace runs.

### Build Phase
- **Goal**: Convert aerobic base into race-specific fitness. Introduce threshold and VO₂max work.
- **Duration**: 6–10 weeks.
- **Intensity**: Zone 2 still dominant (65–70%), add 2–3 threshold/interval sessions per week.
- **Load**: Peak at 100% of target weekly hours by end of Build.
- **Key sessions**: Tempo runs, sweet-spot bike intervals, open-water swims with pace sets.

### Peak Phase (Race-Specific)
- **Goal**: Sharpen fitness, practice race-day execution, introduce specificity.
- **Duration**: 3–4 weeks.
- **Intensity**: Race-pace and above (VO₂max). Reduce total volume by 10–15%, maintain intensity.
- **Key sessions**: Brick workouts (bike → run), race-simulation long days, short time trials.

### Race Phase (Taper + Race)
- **Goal**: Arrive fresh. Reduce fatigue while preserving fitness.
- **Duration**: 1–3 weeks depending on race distance.
- **Intensity**: Keep intensity (short threshold/race-pace), cut volume 30–50% in final week.
- **Key sessions**: Short activation sessions, race-pace efforts of 10–15 min, rest days.

---

## Weekly Load Progression Rules

- **3:1 pattern**: 3 weeks of progressive load followed by 1 recovery week (volume drops 30–40%).
- **Weekly increase cap**: No more than 10% volume increase week-over-week.
- **Recovery week**: Cut volume to prior build-week minus 2 weeks. Keep one quality session.
- **Consecutive hard days**: Avoid placing high-intensity sessions on back-to-back days for the same discipline.

---

## Taper Protocol by Race Distance

| Race Distance | Taper Length | Volume Cut | Intensity |
|---------------|-------------|------------|-----------|
| Sprint        | 5–7 days    | 30–40%     | Maintain |
| Olympic       | 7–10 days   | 40–50%     | Maintain |
| 70.3          | 10–14 days  | 40–50%     | Maintain |
| Full IM       | 14–21 days  | 50–60%     | Reduce slightly |

---

## Discipline Weighting by Experience Level

### Beginner (< 1 year triathlon)
- **Swim**: 35% of training time (biggest fitness return, usually limiting discipline).
- **Bike**: 40% (longest race segment, safest for high volume).
- **Run**: 25% (injury risk is highest; build slowly).

### Intermediate (1–4 years)
- **Swim**: 25%.
- **Bike**: 45%.
- **Run**: 30%.

### Advanced (4+ years, racing regularly)
- **Swim**: 20%.
- **Bike**: 45%.
- **Run**: 35%.

---

## Phase Allocation Formula

Given `weeks_to_race`:
- **Sprint/Olympic** (≤ 26 weeks): Base 40%, Build 35%, Peak 15%, Race 10%.
- **70.3** (≤ 26 weeks): Base 45%, Build 35%, Peak 12%, Race 8%.
- **Full IM** (≤ 30 weeks): Base 50%, Build 30%, Peak 12%, Race 8%.

Minimum phase lengths:
- Base: 4 weeks
- Build: 4 weeks
- Peak: 2 weeks
- Race (taper): 1 week

If `weeks_to_race < 11`, compress by shortening Base first, then Peak.

---

## Session Structure per Week (per Phase)

Each week should contain per discipline:
- **1 long/endurance session** (aerobic base, distance or time).
- **1 quality session** (threshold, intervals, or race-pace — Build/Peak only).
- **1 recovery or technique session** (drills, easy effort).

Rest days: minimum 1 per week, preferably after the longest day.

---

## JSON Output Format

When generating a plan, return a JSON object with this structure:

```json
{
  "phases": [
    {
      "name": "Base",
      "start": "YYYY-MM-DD",
      "end": "YYYY-MM-DD",
      "weeks": 8,
      "weekly_hours": 10.0,
      "sessions": [
        {
          "week": 1,
          "day": "Monday",
          "discipline": "swim",
          "type": "endurance",
          "duration_min": 45,
          "intensity": "zone2",
          "notes": "Easy pace, focus on stroke mechanics"
        }
      ]
    }
  ]
}
```

Every plan must have exactly 4 phases in order: Base, Build, Peak, Race.
`start` of Base = today's date. `end` of Race = A-race date.
